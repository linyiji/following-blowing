from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "app" / "ui" / "frontend"

API_TRIGGER_KEYS = {
    "open_api_settings",
    "test_api_connection",
    "save_api_settings",
    "delete_api_credentials",
    "close_api_settings",
}


def _load_component(monkeypatch: Any):
    def mount(**_kwargs: Any) -> object:
        return object()

    def register(_name: str, **_kwargs: Any):
        return mount

    streamlit = types.ModuleType("streamlit")
    streamlit.components = types.SimpleNamespace(
        v2=types.SimpleNamespace(component=register)
    )
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    for module_name in ("app.ui.component", "app.ui"):
        sys.modules.pop(module_name, None)
    return importlib.import_module("app.ui.component")


def test_api_settings_markup_exposes_complete_byok_controls() -> None:
    html = (FRONTEND / "component.html").read_text(encoding="utf-8")

    for element_id in (
        "apiConnectionStatus",
        "apiSettingsBtn",
        "configureApiBtn",
        "useDemoBtn",
        "aiServices",
        "fastServiceStatus",
        "mainServiceStatus",
        "imageServiceStatus",
        "searchServiceStatus",
        "apiSettingsBackdrop",
        "apiSettingsForm",
        "apiProvider",
        "apiPreset",
        "apiBaseUrl",
        "apiKeyInput",
        "apiFastModel",
        "apiMainModel",
        "apiImageModel",
        "apiFastTimeout",
        "apiMainTimeout",
        "apiImageTimeout",
        "testApiConnectionBtn",
        "advancedImageTestBtn",
        "saveApiSettingsBtn",
        "cancelApiSettingsBtn",
        "deleteApiCredentialsBtn",
        "deleteCredentialConfirm",
        "confirmDeleteApiCredentialsBtn",
    ):
        assert f'id="{element_id}"' in html

    assert 'id="apiKeyInput" name="api_credential" type="password"' in html
    assert 'autocomplete="new-password"' in html
    api_key_tag = html.split('id="apiKeyInput"', 1)[1].split(">", 1)[0]
    assert " value=" not in api_key_tag
    assert "Custom OpenAI Compatible" in html
    assert "TeamoRouter" in html
    assert "gpt-5.6-luna" in html
    assert "gpt-5.6-terra" in html
    assert "gpt-image-2" in html
    assert "删除后 Following blowing 将无法使用真实 AI" in html
    assert "高级图像测试（可能收费）" in html


def test_api_key_is_one_shot_trigger_data_not_component_or_browser_state(
    monkeypatch: Any,
) -> None:
    module = _load_component(monkeypatch)
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")

    assert API_TRIGGER_KEYS <= set(module.TRIGGER_KEYS)
    assert "api_key" not in module.STATE_KEYS
    assert "api_key" not in module.DEFAULT_STATE
    assert 'setStateValue("api_key"' not in javascript
    assert "setStateValue('api_key'" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "data.api_key" not in javascript
    assert "apiSettings.api_key" not in javascript
    assert "runtime.apiKey" not in javascript

    assert "pendingCredentials.get" in javascript
    assert "...(apiKey ? { credential_input: apiKey } : {})" in javascript
    assert "clearCredentialInput();" in javascript
    assert "apiSettings.credential_configured" in javascript
    assert "apiKeyInput.placeholder = credentialConfigured" in javascript


def test_api_settings_events_preserve_readiness_and_demo_contract() -> None:
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")

    for trigger in API_TRIGGER_KEYS:
        assert f'"{trigger}"' in javascript
    assert "apiReadiness.workflow_start_enabled" in javascript
    assert "startButton.disabled = !workflowStartEnabled" in javascript
    assert 'closeApiSettings("use_demo", { use_demo: true })' in javascript
    assert 'emitTrigger("open_api_settings"' in javascript
    assert 'emitTrigger("test_api_connection", payload)' in javascript
    assert 'emitTrigger("save_api_settings", apiSettingsPayload(false, event.currentTarget))' in javascript
    assert 'emitTrigger("delete_api_credentials", { confirmed: true })' in javascript
    assert "testApiConnection(false, event.currentTarget)" in javascript
    assert "testApiConnection(true, event.currentTarget)" in javascript
    assert "advanced_image_test: advancedImageTest" in javascript


def test_teamo_preset_fills_public_fields_but_never_a_credential() -> None:
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")
    preset = javascript.split("const API_PRESETS = {", 1)[1].split(
        "};\n\nconst FALLBACK_AGENTS", 1
    )[0]

    assert 'base_url: "https://api.teamorouter.com/v1"' in preset
    assert 'fast_model: "gpt-5.6-luna"' in preset
    assert 'main_model: "gpt-5.6-terra"' in preset
    assert 'image_model: "gpt-image-2"' in preset
    assert "api_key" not in preset
