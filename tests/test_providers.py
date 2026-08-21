from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.config import IMAGE_MODEL, MODEL_FAST, MODEL_MAIN, ProviderSettings, load_settings
from app.providers import DemoAIProvider, OpenAIProvider, ProviderClient
from app.services import ProviderError, StructuredOutputService


@dataclass
class ExampleOutput:
    name: str
    score: int


class NativeOutput(BaseModel):
    name: str
    score: int


def test_public_configuration_never_exposes_keys(tmp_path):
    settings = load_settings(
        project_root=tmp_path,
        environ={
            "MULTIMODAL_PROVIDER": "openai",
            "MULTIMODAL_API_KEY": "super-secret",
            "MULTIMODAL_MODEL": "configured-model",
            "IMAGE_PROVIDER": "demo",
        },
    )
    public = settings.public_status()
    assert "super-secret" not in repr(public)
    assert "api_key" not in repr(public).lower()


def test_streamlit_secrets_can_select_real_providers_without_leaking_keys(tmp_path):
    settings = load_settings(
        project_root=tmp_path,
        environ={},
        secrets={
            "DEMO_MODE": False,
            "MULTIMODAL_PROVIDER": "openai",
            "MULTIMODAL_API_KEY": "multimodal-secret",
            "MULTIMODAL_MODEL": "gpt-test",
            "MODEL_FAST": "gpt-fast-test",
            "MODEL_MAIN": "gpt-main-test",
            "IMAGE_PROVIDER": "openai",
            "IMAGE_API_KEY": "image-secret",
            "IMAGE_MODEL": "image-test",
            "SEARCH_PROVIDER": "openai",
            "SEARCH_API_KEY": "search-secret",
            "SEARCH_MODEL": "search-test",
            "MAX_PROVIDER_RETRIES": 4,
        },
    )

    assert settings.demo_mode is False
    assert settings.multimodal.configured
    assert settings.image.configured
    assert settings.search.configured
    assert settings.max_provider_retries == 4
    assert settings.model_fast == "gpt-fast-test"
    assert settings.model_main == "gpt-main-test"
    assert settings.image_model == "image-test"
    assert "secret" not in repr(settings.public_status()).lower()


def test_default_routes_and_legacy_main_model_are_compatible(tmp_path):
    defaults = load_settings(project_root=tmp_path, environ={})
    assert defaults.model_fast == MODEL_FAST
    assert defaults.model_main == MODEL_MAIN
    assert defaults.image_model == IMAGE_MODEL

    legacy = load_settings(
        project_root=tmp_path,
        environ={"MULTIMODAL_MODEL": "legacy-terra-alias"},
    )
    assert legacy.model_fast == MODEL_FAST
    assert legacy.model_main == "legacy-terra-alias"


def test_provider_client_retries_retryable_errors_only():
    attempts = 0

    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("temporary")
        return {"ok": True}

    client = ProviderClient(max_retries=1, backoff_seconds=0, sleep=lambda _: None)
    result = client.call("test", flaky)
    assert result.value == {"ok": True}
    assert result.metadata.attempt_count == 2


def test_provider_client_retries_sdk_named_timeout_errors():
    class APITimeoutError(Exception):
        pass

    attempts = 0

    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise APITimeoutError("provider payload must not be echoed")
        return {"ok": True}

    client = ProviderClient(max_retries=1, backoff_seconds=0, sleep=lambda _: None)
    result = client.call("ai.generate_structured", flaky)

    assert result.value == {"ok": True}
    assert result.metadata.attempt_count == 2


def test_structured_output_repairs_exactly_once():
    calls = 0

    def repair(value, error):
        nonlocal calls
        del value, error
        calls += 1
        return {"name": "fixed", "score": 85}

    service = StructuredOutputService(max_repairs=1)
    value = service.parse("invalid", ExampleOutput, repair=repair)
    assert value == ExampleOutput(name="fixed", score=85)
    assert calls == 1


def test_demo_and_unconfigured_real_provider_share_contract():
    demo = DemoAIProvider({"fixture": {"name": "demo", "score": 90}})
    output = demo.generate_structured(prompt="fixture", response_model=ExampleOutput)
    assert output.score == 90

    real = OpenAIProvider(ProviderSettings(provider="openai", model=None, api_key=None))
    with pytest.raises(ProviderError, match="not configured"):
        real.generate_text(prompt="hello")


def test_openai_provider_routes_native_structured_and_vision_calls(tmp_path):
    image = tmp_path / "reference.png"
    image.write_bytes(b"png")

    class FakeResponses:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def parse(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                status="completed",
                output=[],
                output_parsed=NativeOutput(name="ok", score=91),
            )

    responses = FakeResponses()
    provider = OpenAIProvider(
        ProviderSettings(provider="openai", model="legacy", api_key="test-key"),
        model_fast="gpt-5.6-luna",
        model_main="gpt-5.6-terra",
        client=ProviderClient(max_retries=0),
    )
    provider._sdk_client = SimpleNamespace(responses=responses)

    fast = provider.generate_structured(
        prompt="fast",
        response_model=NativeOutput,
        model_role="fast",
        demo_output={"must": "not leak"},
    )
    main = provider.analyze_multimodal(
        images=[image],
        prompt="vision",
        response_model=NativeOutput,
        model_role="main",
    )
    auto_detail = provider.analyze_multimodal(
        images=[image],
        prompt="brand vision",
        response_model=NativeOutput,
        model_role="main",
        image_detail="auto",
    )

    assert fast.score == main.score == auto_detail.score == 91
    assert [call["model"] for call in responses.calls] == [
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-terra",
    ]
    vision_content = responses.calls[1]["input"][0]["content"]
    assert vision_content[1]["type"] == "input_image"
    assert vision_content[1]["detail"] == "high"
    assert responses.calls[2]["input"][0]["content"][1]["detail"] == "auto"
    assert "must" not in str(responses.calls[0]["input"])

    with pytest.raises(ValueError, match="Unsupported image detail"):
        provider.analyze_multimodal(
            images=[image],
            prompt="invalid detail",
            response_model=NativeOutput,
            image_detail="maximum",
        )


def test_openai_sdk_retries_are_disabled_because_provider_client_governs_retries(
    monkeypatch,
):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(__import__("sys").modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    provider = OpenAIProvider(
        ProviderSettings(
            provider="openai",
            model="gpt-5.6-terra",
            api_key="test-key",
            base_url="https://provider.invalid/v1",
        )
    )

    provider._require_sdk()

    assert captured["max_retries"] == 0
