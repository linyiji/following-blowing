from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.settings import (
    APISettingsService,
    TEAMO_BASE_URL,
    ApiSettings,
    CredentialStore,
    KeyringCredentialStore,
    RuntimeProviderConfig,
    SessionCredentialStore,
    SettingsRepository,
    SettingsRepositoryError,
    default_settings_path,
)
from app.settings.connection import ProviderConnectionTester


DUMMY_TEST_TOKEN = "DUMMY_TEST_TOKEN"


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, account: str, secret: str) -> None:
        self.values[(service, account)] = secret

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def delete_password(self, service: str, account: str) -> None:
        self.values.pop((service, account), None)


class UnavailableKeyring:
    def set_password(self, service: str, account: str, secret: str) -> None:
        raise RuntimeError("no secure keychain")

    def get_password(self, service: str, account: str) -> str | None:
        raise RuntimeError("no secure keychain")

    def delete_password(self, service: str, account: str) -> None:
        raise RuntimeError("no secure keychain")


class CountingSessionStore(SessionCredentialStore):
    def __init__(self) -> None:
        super().__init__()
        self.set_calls = 0
        self.delete_calls = 0

    def set_secret(self, secret: str):  # type: ignore[no-untyped-def]
        self.set_calls += 1
        return super().set_secret(secret)

    def delete(self):  # type: ignore[no-untyped-def]
        self.delete_calls += 1
        return super().delete()


def make_service(
    tmp_path: Path,
    *,
    keyring_module: object | None = None,
    fallback: SessionCredentialStore | None = None,
) -> APISettingsService:
    preferred = KeyringCredentialStore(keyring_module=keyring_module or FakeKeyring())
    credentials = CredentialStore(preferred=preferred, fallback=fallback)
    return APISettingsService(
        repository=SettingsRepository(tmp_path / "settings.json"),
        credential_store=credentials,
    )


def assert_secret_absent(payload: object, secret: str) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    assert secret not in serialized
    assert "api_key" not in serialized.lower()


def test_default_path_prefers_macos_application_support(tmp_path: Path) -> None:
    assert default_settings_path(home=tmp_path, platform="darwin") == (
        tmp_path
        / "Library"
        / "Application Support"
        / "Following blowing"
        / "settings.json"
    )


def test_repository_round_trip_is_non_sensitive_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "settings.json"
    repository = SettingsRepository(path)
    settings = ApiSettings(
        provider="openai_compatible",
        base_url="https://example.test/v1/",
        fast_timeout=30,
        main_timeout=90,
        image_timeout=150,
    )

    assert repository.save(settings) == settings
    assert repository.load() == settings
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8"))["base_url"] == (
        "https://example.test/v1"
    )

    with pytest.raises(SettingsRepositoryError):
        repository.save({**settings.model_dump(), "api_key": "must-not-write"})
    assert "must-not-write" not in path.read_text(encoding="utf-8")


def test_settings_validate_provider_url_and_positive_timeouts() -> None:
    assert ApiSettings(provider="openai").provider == "openai"
    assert ApiSettings(provider="openai_compatible").provider == "openai_compatible"
    with pytest.raises(ValidationError):
        ApiSettings(provider="other")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ApiSettings(base_url="https://user:placeholder@example.test/v1")
    with pytest.raises(ValidationError):
        ApiSettings(fast_timeout=0)


def test_service_accepts_nested_timeouts_and_public_view_is_flat_safe(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    secret = DUMMY_TEST_TOKEN

    result = service.save(
        {
            "provider": "openai_compatible",
            "base_url": "https://example.test/v1",
            "model_fast": "fast-test",
            "model_main": "main-test",
            "image_model": "image-test",
            "timeouts": {"fast": 11, "main": 22, "image": 33},
        },
        api_key=secret,
    )
    assert result.credential.configured is True

    public = service.public_view()
    assert public["fast_timeout"] == 11
    assert public["main_timeout"] == 22
    assert public["image_timeout"] == 33
    assert public["credential_configured"] is True
    assert public["session_only"] is False
    assert public["storage_warning"] is None
    assert_secret_absent(public, secret)


def test_successfully_tested_key_is_one_shot_for_matching_save(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    settings = ApiSettings(base_url="https://example.test/v1")

    service.stage_verified_credential(settings, DUMMY_TEST_TOKEN)

    assert service.consume_verified_credential(settings) == DUMMY_TEST_TOKEN
    assert service.consume_verified_credential(settings) is None
    assert DUMMY_TEST_TOKEN not in repr(service)


def test_tested_key_cannot_save_changed_provider_settings(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    tested = ApiSettings(base_url="https://example.test/v1", model_main="main-a")
    changed = tested.model_copy(update={"model_main": "main-b"})

    service.stage_verified_credential(tested, DUMMY_TEST_TOKEN)

    assert service.consume_verified_credential(changed) is None
    assert service.consume_verified_credential(tested) == DUMMY_TEST_TOKEN


def test_failed_test_can_clear_staged_key(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    settings = ApiSettings(base_url="https://example.test/v1")
    service.stage_verified_credential(settings, DUMMY_TEST_TOKEN)

    service.clear_verified_credential()

    assert service.consume_verified_credential(settings) is None


def test_keyring_credential_persists_but_status_reopen_and_delete_are_safe(
    tmp_path: Path,
) -> None:
    keyring = FakeKeyring()
    service = make_service(tmp_path, keyring_module=keyring)
    secret = DUMMY_TEST_TOKEN
    service.save(ApiSettings(), api_key=secret)

    status = service.credential_status()
    assert status.configured is True
    assert status.persistent is True
    assert status.backend == "keyring"
    assert_secret_absent(status.model_dump(mode="json"), secret)

    reopened_service = make_service(tmp_path, keyring_module=keyring)
    reopened = reopened_service.reopen()
    assert reopened.credential.configured is True
    assert_secret_absent(reopened.model_dump(mode="json"), secret)

    runtime = reopened_service.runtime_config(require_credential=True)
    assert isinstance(runtime, RuntimeProviderConfig)
    assert runtime.api_key_value() == secret
    assert_secret_absent(runtime.model_dump(mode="json"), secret)
    assert secret not in repr(runtime)

    deleted = reopened_service.delete()
    assert deleted.configured is False
    assert_secret_absent(deleted.model_dump(mode="json"), secret)
    assert reopened_service.runtime_config().api_key_value() is None


def test_unavailable_keyring_falls_back_to_session_only_and_never_plaintext(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path, keyring_module=UnavailableKeyring())
    secret = DUMMY_TEST_TOKEN

    status = service.save_api_key(secret, persistent=True)
    assert status.configured is True
    assert status.persistent is False
    assert status.backend == "session"
    public = service.public_view()
    assert public["session_only"] is True
    assert isinstance(public["storage_warning"], str)
    assert service.runtime_config().api_key_value() == secret

    # The only file this layer writes is the non-sensitive settings JSON.
    service.save(ApiSettings(base_url="https://example.test/v1"))
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text(encoding="utf-8")

    # A fresh process-level store cannot recover the session-only key.
    fresh = make_service(tmp_path, keyring_module=UnavailableKeyring())
    assert fresh.credential_status().configured is False
    assert fresh.runtime_config().api_key_value() is None


def test_teamo_preset_updates_only_safe_fields_and_never_mutates_key(
    tmp_path: Path,
) -> None:
    fallback = CountingSessionStore()
    service = make_service(tmp_path, fallback=fallback)
    secret = DUMMY_TEST_TOKEN
    service.save(
        ApiSettings(
            provider="openai_compatible",
            fast_timeout=13,
            main_timeout=29,
            image_timeout=47,
        ),
        api_key=secret,
        persist_credential=False,
    )
    set_calls = fallback.set_calls
    delete_calls = fallback.delete_calls

    snapshot = service.apply_teamo_preset()
    assert snapshot.settings.base_url == TEAMO_BASE_URL
    assert snapshot.settings.model_fast == "gpt-5.6-luna"
    assert snapshot.settings.model_main == "gpt-5.6-terra"
    assert snapshot.settings.image_model == "gpt-image-2"
    assert snapshot.settings.provider == "openai_compatible"
    assert snapshot.settings.fast_timeout == 13
    assert snapshot.settings.main_timeout == 29
    assert snapshot.settings.image_timeout == 47
    assert fallback.set_calls == set_calls
    assert fallback.delete_calls == delete_calls
    assert service.runtime_config().api_key_value() == secret
    assert secret not in (tmp_path / "settings.json").read_text(encoding="utf-8")


class FakeModelsAPI:
    def __init__(
        self,
        model_ids: list[str] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.model_ids = model_ids or []
        self.error = error
        self.calls = 0

    def list(self) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            data=[SimpleNamespace(id=model_id) for model_id in self.model_ids]
        )


class FakeResponsesAPI:
    def __init__(self, *, errors: dict[str, Exception] | None = None) -> None:
        self.errors = errors or {}
        self.calls: list[dict[str, str]] = []

    def create(self, *, model: str, input: str) -> Any:
        self.calls.append({"model": model, "input": input})
        if model in self.errors:
            raise self.errors[model]
        return SimpleNamespace(output_text="OK")


class FakeImagesAPI:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def generate(self, **kwargs: str) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(data=[])


class FakeProviderClient:
    def __init__(
        self,
        *,
        model_ids: list[str] | None = None,
        catalog_error: Exception | None = None,
    ) -> None:
        self.models = FakeModelsAPI(model_ids, error=catalog_error)
        self.responses = FakeResponsesAPI()
        self.images = FakeImagesAPI()


class FakeHTTPError(RuntimeError):
    def __init__(self, status_code: int, unsafe_detail: str = "unsafe detail") -> None:
        super().__init__(unsafe_detail)
        self.status_code = status_code


def runtime_config(*, with_key: bool = True) -> RuntimeProviderConfig:
    return RuntimeProviderConfig(
        provider="openai_compatible",
        base_url="https://gateway.example.test/v1",
        model_fast="fast-model",
        model_main="main-model",
        image_model="image-model",
        fast_timeout=10,
        main_timeout=20,
        image_timeout=30,
        api_key=SecretStr(DUMMY_TEST_TOKEN) if with_key else None,
        credential_backend="session" if with_key else "none",
    )


def test_connection_catalog_and_fast_main_text_checks_pass_without_network() -> None:
    client = FakeProviderClient(
        model_ids=["fast-model", "main-model", "image-model"]
    )
    tester = ProviderConnectionTester(client_factory=lambda config: client)

    result = tester.test(runtime_config())

    assert result.ok is True
    assert result.provider_reachable is True
    assert result.catalog_supported is True
    assert [(check.name, check.status) for check in result.checks] == [
        ("provider", "pass"),
        ("fast", "pass"),
        ("main", "pass"),
        ("image", "pass"),
    ]
    assert [call["model"] for call in client.responses.calls] == [
        "fast-model",
        "main-model",
    ]


def test_standard_connection_test_never_calls_image_generation() -> None:
    client = FakeProviderClient(
        model_ids=["fast-model", "main-model", "image-model"]
    )
    tester = ProviderConnectionTester(client_factory=lambda config: client)

    result = tester.test(runtime_config())

    assert result.ok is True
    assert result.image_generation_performed is False
    assert client.images.calls == []


def test_unsupported_catalog_continues_with_fast_and_main_text_checks() -> None:
    client = FakeProviderClient(catalog_error=FakeHTTPError(405))
    tester = ProviderConnectionTester(client_factory=lambda config: client)

    result = tester.test(runtime_config())

    assert result.ok is True
    assert result.catalog_supported is False
    assert result.checks[0].name == "provider"
    assert result.checks[0].status == "unverified"
    assert [call["model"] for call in client.responses.calls] == [
        "fast-model",
        "main-model",
    ]
    assert result.checks[-1].name == "image"
    assert result.checks[-1].status == "unverified"
    assert client.images.calls == []


def test_catalog_missing_fast_model_fails_before_text_or_image_calls() -> None:
    client = FakeProviderClient(model_ids=["main-model", "image-model"])
    tester = ProviderConnectionTester(client_factory=lambda config: client)

    result = tester.test(runtime_config())

    assert result.ok is False
    assert result.error_code == "model_unavailable"
    assert result.checks[-1].name == "fast"
    assert result.checks[-1].status == "fail"
    assert client.responses.calls == []
    assert client.images.calls == []


def test_catalog_missing_main_model_fails_after_fast_text_check() -> None:
    client = FakeProviderClient(model_ids=["fast-model", "image-model"])
    tester = ProviderConnectionTester(client_factory=lambda config: client)

    result = tester.test(runtime_config())

    assert result.ok is False
    assert result.error_code == "model_unavailable"
    assert result.checks[-1].name == "main"
    assert [call["model"] for call in client.responses.calls] == ["fast-model"]
    assert client.images.calls == []


def test_catalog_missing_image_model_reports_failure_without_generating() -> None:
    client = FakeProviderClient(model_ids=["fast-model", "main-model"])
    tester = ProviderConnectionTester(client_factory=lambda config: client)

    result = tester.test(runtime_config())

    assert result.ok is False
    assert result.error_code == "model_unavailable"
    assert result.checks[-1].name == "image"
    assert result.checks[-1].status == "unverified"
    assert len(client.responses.calls) == 2
    assert client.images.calls == []


def test_authentication_failure_result_is_browser_safe() -> None:
    unsafe_detail = (
        f"Authorization {DUMMY_TEST_TOKEN} rejected at "
        "https://gateway.example.test/private/request/123"
    )
    client = FakeProviderClient(catalog_error=FakeHTTPError(401, unsafe_detail))
    tester = ProviderConnectionTester(client_factory=lambda config: client)

    result = tester.test(runtime_config())
    public = result.public_view()
    serialized = json.dumps(public, ensure_ascii=False)

    assert result.ok is False
    assert result.error_code == "authentication_failed"
    assert result.message == "Authentication failed. Check the API credential."
    assert DUMMY_TEST_TOKEN not in serialized
    assert unsafe_detail not in serialized
    assert "gateway.example.test" not in serialized


def test_missing_key_short_circuits_before_constructing_provider_client() -> None:
    factory_calls = 0

    def client_factory(config: RuntimeProviderConfig) -> FakeProviderClient:
        nonlocal factory_calls
        factory_calls += 1
        return FakeProviderClient()

    result = ProviderConnectionTester(client_factory=client_factory).test(
        runtime_config(with_key=False)
    )

    assert result.ok is False
    assert result.error_code == "authentication_missing"
    assert factory_calls == 0
    assert_secret_absent(result.public_view(), DUMMY_TEST_TOKEN)


def test_only_explicit_advanced_image_test_calls_generation() -> None:
    client = FakeProviderClient(
        model_ids=["fast-model", "main-model", "image-model"]
    )
    tester = ProviderConnectionTester(client_factory=lambda config: client)

    standard = tester.test(runtime_config())
    assert standard.ok is True
    assert client.images.calls == []

    advanced = tester.test_image(runtime_config())
    assert advanced.ok is True
    assert advanced.image_generation_performed is True
    assert len(client.images.calls) == 1
    assert client.images.calls[0] == {
        "model": "image-model",
        "prompt": "A single neutral blue circle on a white background.",
        "size": "1024x1024",
    }
