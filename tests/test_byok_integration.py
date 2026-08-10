from __future__ import annotations

import ast
import json
import tomllib
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.config import apply_runtime_provider_config, load_settings
from app.health import AppBootstrap
from app.providers import ProviderFactory
from app.providers.openai_ai import OpenAIProvider
from app.providers.openai_image import OpenAIImageProvider
from app.providers.search_mock import MockSearchProvider
from app.services.export_service import ExportService
from app.services.run_service import LocalRunRepository
from app.settings.models import RuntimeProviderConfig
from scripts.secret_scan import (
    find_runtime_credential_files,
    scan_source_credentials,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "app" / "ui" / "frontend"

API_SETTING_TRIGGERS = {
    "open_api_settings",
    "test_api_connection",
    "save_api_settings",
    "delete_api_credentials",
    "close_api_settings",
}


def _credential() -> str:
    # Constructed at runtime so this release test never embeds a key-shaped
    # credential fixture that could be mistaken for a bundled secret.
    return "-".join(("integration", "credential", "not", "for", "network"))


def _runtime_config(**updates: Any) -> RuntimeProviderConfig:
    values: dict[str, Any] = {
        "provider": "openai_compatible",
        "base_url": "https://provider.invalid/v1",
        "model_fast": "byok-fast",
        "model_main": "byok-main",
        "image_model": "byok-image",
        "fast_timeout": 17,
        "main_timeout": 29,
        "image_timeout": 41,
        "api_key": SecretStr(_credential()),
        "credential_backend": "session",
    }
    values.update(updates)
    return RuntimeProviderConfig(**values)


def _all_mapping_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key).lower())
            keys.update(_all_mapping_keys(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            keys.update(_all_mapping_keys(nested))
    return keys


def _literal_assignment(source: str, name: str) -> Any:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} was not defined as a literal")


def test_byok_runtime_overrides_environment_and_admin_configuration() -> None:
    environment_credential = "-".join(("environment", "credential"))
    admin_credential = "-".join(("administrator", "credential"))
    base = load_settings(
        project_root=PROJECT_ROOT,
        secrets={
            "MULTIMODAL_PROVIDER": "openai",
            "MULTIMODAL_API_KEY": admin_credential,
            "IMAGE_PROVIDER": "openai",
            "IMAGE_API_KEY": admin_credential,
            "MODEL_FAST": "admin-fast",
            "MODEL_MAIN": "admin-main",
            "IMAGE_MODEL": "admin-image",
        },
        environ={
            "MULTIMODAL_PROVIDER": "openai",
            "MULTIMODAL_API_KEY": environment_credential,
            "IMAGE_PROVIDER": "openai",
            "IMAGE_API_KEY": environment_credential,
            "MODEL_FAST": "environment-fast",
            "MODEL_MAIN": "environment-main",
            "IMAGE_MODEL": "environment-image",
            "DEMO_MODE": "false",
        },
    )
    assert base.model_fast == "environment-fast"
    assert base.multimodal.api_key == environment_credential

    runtime = _runtime_config()
    resolved = apply_runtime_provider_config(base, runtime)

    assert resolved.provider_source == "byok"
    assert resolved.demo_mode is False
    assert resolved.model_fast == "byok-fast"
    assert resolved.model_main == "byok-main"
    assert resolved.image_model == "byok-image"
    assert resolved.multimodal.api_key == _credential()
    assert resolved.image.api_key == _credential()
    assert resolved.multimodal.base_url == "https://provider.invalid/v1"
    assert resolved.multimodal.timeout == 29
    assert resolved.image.timeout == 41


def test_provider_factory_accepts_runtime_config_and_keeps_ai_sdk_lazy() -> None:
    provider = ProviderFactory(_runtime_config()).create_ai()

    assert isinstance(provider, OpenAIProvider)
    assert provider.model_fast == "byok-fast"
    assert provider.model_main == "byok-main"
    assert provider._sdk_client is None


def test_provider_factory_accepts_runtime_config_and_keeps_image_sdk_lazy() -> None:
    provider = ProviderFactory(_runtime_config()).create_image()

    assert isinstance(provider, OpenAIImageProvider)
    assert provider.settings.model == "byok-image"
    assert provider._sdk_client is None


def test_byok_provider_factory_always_keeps_search_in_mock_mode() -> None:
    factory = ProviderFactory(_runtime_config())

    assert factory.settings.search.is_demo is True
    assert factory.settings.search_mode == "demo"
    assert isinstance(factory.create_search(), MockSearchProvider)


def test_app_public_status_contains_routes_but_no_credential() -> None:
    base = load_settings(environ={}, project_root=PROJECT_ROOT)
    settings = apply_runtime_provider_config(base, _runtime_config())

    status = settings.public_status()
    serialized = json.dumps(status, ensure_ascii=False)

    assert status["provider_source"] == "byok"
    assert status["model_routes"] == {
        "fast": "byok-fast",
        "main": "byok-main",
        "image": "byok-image",
    }
    assert _credential() not in serialized
    assert "api_key" not in _all_mapping_keys(status)


def test_runtime_provider_config_excludes_credential_from_every_public_dump() -> None:
    runtime = _runtime_config()

    dumped = runtime.model_dump(mode="json")
    public = runtime.public_view()

    assert runtime.api_key_value() == _credential()
    assert "api_key" not in dumped
    assert "api_key" not in public
    assert public["credential_configured"] is True
    assert _credential() not in runtime.model_dump_json()
    assert _credential() not in json.dumps(public, ensure_ascii=False)
    assert _credential() not in repr(runtime)


def test_no_key_bootstrap_runs_in_demo_mode_without_provider_import_or_network(
    tmp_path: Path,
) -> None:
    settings = load_settings(environ={}, project_root=PROJECT_ROOT)
    settings = replace(settings, data_dir=tmp_path / "runtime-data")

    health = AppBootstrap(settings).run()

    assert settings.multimodal.api_key is None
    assert settings.image.api_key is None
    assert health.status == "DEMO_MODE"
    assert health.luna_ready is True
    assert health.terra_ready is True
    assert health.image_provider_ready is True
    assert health.search_mode == "demo"


def test_missing_configuration_selects_automatic_not_explicit_demo() -> None:
    settings = load_settings(environ={}, project_root=PROJECT_ROOT)

    assert settings.demo_mode is True
    assert settings.demo_explicit is False
    assert settings.provider_source == "demo"


def test_explicit_demo_is_distinguishable_from_automatic_fallback() -> None:
    automatic = load_settings(environ={}, project_root=PROJECT_ROOT)
    explicit = load_settings(
        environ={"DEMO_MODE": "true"},
        project_root=PROJECT_ROOT,
    )

    assert automatic.demo_mode is True
    assert automatic.demo_explicit is False
    assert explicit.demo_mode is True
    assert explicit.demo_explicit is True


def test_byok_health_is_ready_without_claiming_image_smoke_or_live_search(
    tmp_path: Path,
) -> None:
    base = load_settings(environ={}, project_root=PROJECT_ROOT)
    settings = apply_runtime_provider_config(base, _runtime_config())
    settings = replace(settings, data_dir=tmp_path / "runtime-data")

    health = AppBootstrap(settings).run()

    assert health.status == "READY"
    assert health.provider_mode == "live"
    assert health.luna_ready is True
    assert health.terra_ready is True
    assert health.image_provider_ready is True
    assert health.image_provider_configured is True
    assert health.image_provider_verified is False
    assert health.model_catalog_verified is False
    assert health.search_provider_ready is True
    assert health.search_mode == "demo"


def test_credential_never_enters_run_checkpoint_or_export_archive(
    tmp_path: Path,
) -> None:
    runtime = _runtime_config()
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run(
        provider_mode="live",
        provider_source="byok",
        runtime_provider=runtime,
    )
    checkpoint = {
        "run_id": run["run_id"],
        "status": "CREATED",
        "runtime_provider": runtime,
    }
    repository.save_checkpoint(run["run_id"], checkpoint)
    archive = ExportService(repository).create_zip(
        run["run_id"],
        {
            "runtime.json": runtime,
            "workflow_trace.json": checkpoint,
            "readme.md": "BYOK workflow export",
        },
    )

    persisted_run = repository.get_run(run["run_id"])
    persisted_checkpoint = repository.get_checkpoint(run["run_id"])
    assert "api_key" not in _all_mapping_keys(persisted_run)
    assert "api_key" not in _all_mapping_keys(persisted_checkpoint)

    for path in repository.run_dir(run["run_id"]).rglob("*"):
        if path.is_file() and path != archive:
            assert _credential().encode() not in path.read_bytes()
    with zipfile.ZipFile(archive) as package:
        for name in package.namelist():
            assert _credential().encode() not in package.read(name)


def test_release_contains_no_runtime_streamlit_secrets_file() -> None:
    assert find_runtime_credential_files(PROJECT_ROOT) == []


def test_byok_build_info_declares_credential_free_twelve_agent_edition() -> None:
    payload = json.loads(
        (PROJECT_ROOT / "BYOK_BUILD_INFO.json").read_text(encoding="utf-8")
    )

    assert payload["product"] == "Following blowing"
    assert payload["edition"] == "byok"
    assert payload["workflow_agents"] == 12
    assert payload["bundled_credentials"] is False
    assert payload["search_mode"] == "demo"
    assert payload["multi_reference_image_edit"] == "UNVERIFIED"


def test_admin_secrets_example_contains_only_empty_values() -> None:
    example = PROJECT_ROOT / ".streamlit" / "secrets.toml.example"
    values = tomllib.loads(example.read_text(encoding="utf-8"))

    assert {
        "MULTIMODAL_API_KEY",
        "IMAGE_API_KEY",
        "SEARCH_API_KEY",
        "OPENAI_API_KEY",
    } <= set(values)
    assert all(value == "" for value in values.values())


def test_frontend_has_no_browser_credential_persistence_channel() -> None:
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")
    html = (FRONTEND / "component.html").read_text(encoding="utf-8")

    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert 'setStateValue("api_key"' not in javascript
    assert "setStateValue('api_key'" not in javascript
    assert "data.api_key" not in javascript
    assert "apiSettings.api_key" not in javascript
    assert "runtime.apiKey" not in javascript
    assert "clearCredentialInput();" in javascript

    input_tag = html.split('id="apiKeyInput"', 1)[1].split(">", 1)[0]
    assert 'type="password"' in input_tag
    assert " value=" not in input_tag


def test_api_settings_trigger_names_match_python_and_frontend_contract() -> None:
    python_source = (PROJECT_ROOT / "app" / "ui" / "component.py").read_text(
        encoding="utf-8"
    )
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")
    trigger_keys = set(_literal_assignment(python_source, "TRIGGER_KEYS"))

    assert API_SETTING_TRIGGERS <= trigger_keys
    for trigger in API_SETTING_TRIGGERS:
        assert f'"{trigger}"' in javascript


def test_release_secret_scan_finds_no_credential_shaped_value() -> None:
    assert scan_source_credentials(PROJECT_ROOT) == []
