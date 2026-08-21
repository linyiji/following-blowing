from __future__ import annotations

import importlib
import re
import sys
import types
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "app" / "ui" / "frontend"

STATE_KEYS = {
    "ip_image",
    "brand_image",
    "image_pair",
    "advance_request",
    "selected_goals",
    "goal_text",
    "ai_suggestion",
    "page_state",
}

TRIGGER_KEYS = {
    "ai_supplement",
    "adopt_suggestion",
    "regenerate_suggestion",
    "clear_goal",
    "start_workflow",
    "advance_workflow",
    "open_agent_detail",
    "export_package",
    "retry_agent",
    "open_api_settings",
    "test_api_connection_with_credential",
    "test_api_connection",
    "save_api_settings_with_credential",
    "save_api_settings",
    "delete_api_credentials",
    "close_api_settings",
}


def _load_with_fake_streamlit(monkeypatch: Any):
    registrations: list[tuple[str, dict[str, Any]]] = []
    mounts: list[dict[str, Any]] = []
    result = object()

    def mount(**kwargs: Any):
        mounts.append(kwargs)
        return result

    def register(name: str, **kwargs: Any):
        registrations.append((name, kwargs))
        return mount

    streamlit = types.ModuleType("streamlit")
    streamlit.components = types.SimpleNamespace(
        v2=types.SimpleNamespace(component=register)
    )
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    for module_name in ("app.ui.component", "app.ui"):
        sys.modules.pop(module_name, None)

    module = importlib.import_module("app.ui.component")
    return module, registrations, mounts, result


def test_component_registers_split_sources_once(monkeypatch: Any) -> None:
    module, registrations, _, _ = _load_with_fake_streamlit(monkeypatch)

    assert len(registrations) == 1
    name, registration = registrations[0]
    assert name == module.COMPONENT_NAME == "ai_ip_brand_workflow"
    assert registration == {
        "html": (FRONTEND / "component.html").read_text(encoding="utf-8"),
        "css": (FRONTEND / "component.css").read_text(encoding="utf-8"),
        "js": (FRONTEND / "component.js").read_text(encoding="utf-8"),
        "isolate_styles": True,
    }


def test_wrapper_mounts_all_state_and_trigger_callbacks(monkeypatch: Any) -> None:
    module, _, mounts, sentinel = _load_with_fake_streamlit(monkeypatch)
    supplied_data = {"demo_mode": True, "workflow_snapshot": {"status": "ready"}}
    supplied_defaults = {"goal_text": "用户原始输入"}

    returned = module.render_component(
        supplied_data,
        supplied_defaults,
        key="frontend-contract",
    )

    assert returned is sentinel
    assert len(mounts) == 1
    mounted = mounts[0]
    assert mounted["data"] == supplied_data
    assert mounted["key"] == "frontend-contract"
    assert set(mounted["default"]) == STATE_KEYS
    assert mounted["default"]["goal_text"] == "用户原始输入"
    assert mounted["default"]["selected_goals"] == []
    assert module.STATE_KEYS == tuple(module.DEFAULT_STATE)

    expected_callbacks = {
        f"on_{name}_change" for name in STATE_KEYS | TRIGGER_KEYS
    }
    actual_callbacks = {
        name for name in mounted if name.startswith("on_")
    }
    assert actual_callbacks == expected_callbacks
    assert all(callable(mounted[name]) for name in expected_callbacks)


def test_frontend_uses_v2_bidirectional_contract_without_html_sinks() -> None:
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")

    assert "export default function(component)" in javascript
    assert "parentElement.querySelector" in javascript
    assert "setStateValue" in javascript
    assert "setTriggerValue" in javascript
    assert "return () =>" in javascript
    assert "removeEventListener" in javascript
    assert "innerHTML" not in javascript
    assert "outerHTML" not in javascript
    assert "insertAdjacentHTML" not in javascript

    for state_key in STATE_KEYS:
        assert f'"{state_key}"' in javascript
    for trigger_key in TRIGGER_KEYS:
        assert f'"{trigger_key}"' in javascript

    for event_field in ("event_id", "run_id", "revision", "dedupe_token"):
        assert event_field in javascript
    assert "runtime.autoAdvanceTokens" in javascript
    assert 'stateKey: "advance_request"' in javascript
    assert "setStateValue(options.stateKey, event)" in javascript
    assert "FileReader" in javascript
    read_upload = javascript.split("const readUpload =", 1)[1].split(
        "reader.readAsDataURL(file);", 1
    )[0]
    reader_lifecycle = read_upload.split("const reader = new FileReader();", 1)[1]
    assert reader_lifecycle.index("reader.onload =") < reader_lifecycle.index(
        'input.value = "";'
    )
    assert "reader.onabort" in reader_lifecycle
    assert 'setStateValue("image_pair"' in javascript
    assert 'adoptSuggestionButton.textContent = suggestionAdopted ? "✓ 已采用"' in javascript
    assert "50 * 1024 * 1024" in javascript
    assert "demoAssetFor" not in javascript
    assert "image/png" in javascript
    assert "image/jpeg" in javascript
    assert "URL.createObjectURL" in javascript
    assert 'guardianVerdict === "PASS"' in javascript
    assert "workflowComplete" in javascript


def test_migrated_markup_and_css_preserve_the_visual_contract() -> None:
    html = (FRONTEND / "component.html").read_text(encoding="utf-8")
    css = (FRONTEND / "component.css").read_text(encoding="utf-8")

    assert "data:image/" not in html
    assert "<script" not in html
    assert "<style" not in html
    assert 'id="ipFileInput"' in html
    assert 'id="brandFileInput"' in html
    assert 'accept="image/png,image/jpeg,image/webp"' in html
    assert 'data-value="帽子 / 头饰"' in html
    assert 'aria-live="polite"' in html
    assert 'role="dialog"' in html

    for element_id in (
        "toast",
        "ipPreview",
        "brandPreview",
        "goalOptions",
        "goalText",
        "aiSupplementBtn",
        "startBtn",
        "workflowStage",
        "resultSection",
        "exportBtn",
        "modalBackdrop",
    ):
        assert f'id="{element_id}"' in html

    for baseline_rule in (
        "width:min(1220px,92vw)",
        "border-radius:24px",
        "box-shadow:0 10px 30px rgba(15,23,42,.07)",
        "transform:translateX(-130%)",
        "grid-template-columns:repeat(3,minmax(0,1fr))",
        "position:fixed;top:24px;left:50%",
        "@media(max-width:820px)",
        "@media(max-width:540px)",
    ):
        assert baseline_rule in css
    assert ":host" in css


def test_backend_notifications_use_the_existing_toast() -> None:
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")

    assert "data.notification" in javascript
    assert "lastNotificationToken" in javascript
    assert "showToast(notificationMessage)" in javascript


def test_frontend_presents_12_agent_identity_grammar_workflow() -> None:
    html = (FRONTEND / "component.html").read_text(encoding="utf-8")
    css = (FRONTEND / "component.css").read_text(encoding="utf-8")
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")
    fallback_catalog = javascript.split("const FALLBACK_AGENTS = [", 1)[1].split(
        "];\n\nconst SCORE_LABELS", 1
    )[0]
    names = re.findall(r'^\s+name: "([^"]+ Agent)",$', fallback_catalog, re.MULTILINE)

    assert names == [
        "IP Preparation Agent",
        "IP Intelligence Agent",
        "Brand Intelligence Agent",
        "Brand Collaboration Agent",
        "Brand Feature Agent",
        "Creative Brief Agent",
        "Fusion Decision Agent",
        "IP Adaptation Agent",
        "Fusion Generation Agent",
        "IP Guardian Agent",
        "Ranking Agent",
        "Design Package Agent",
    ]
    assert javascript.index('name: "Fusion Decision Agent"') < javascript.index(
        'name: "IP Adaptation Agent"'
    ) < javascript.index('name: "Fusion Generation Agent"')
    assert "IP Identity Grammar" in html
    assert "IP Identity Grammar" in javascript
    assert "12-Agent Workflow" in html
    assert "3 列 × 4 行" in html
    assert "Identity Lock" not in html
    assert "Identity Lock" not in javascript

    # Twelve completed Agents occupy the existing desktop 3-column grid,
    # producing four equal-height rows without changing the responsive layout.
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in css
    assert "grid-auto-rows:minmax(126px,auto)" in css
    assert "grid.dataset.agentCount = String(ordered.length)" in javascript
    assert "@media(max-width:820px)" in css
    assert "@media(max-width:540px)" in css


def test_adaptation_and_guardian_modals_expose_pose_aware_contract() -> None:
    javascript = (FRONTEND / "component.js").read_text(encoding="utf-8")

    for label in (
        "Role",
        "Inputs",
        "Target Pose",
        "Pose Blueprint",
        "Identity Anchors",
        "Allowed Transformations",
        "Brand Attachments",
        "Occlusion Rules",
        "Generation Instructions",
        "Handoff",
    ):
        assert f'appendDetailBlock("{label}"' in javascript

    for label in (
        "Original Pose",
        "Target Pose",
        "Candidate Pose",
        "Allowed Transformation",
        "Identity Drift",
        "Pose Compliance",
        "Brand Integration Compliance",
        "Identity Score",
        "Verdict",
        "Revision",
    ):
        assert f'appendDetailBlock("{label}"' in javascript

    for field in (
        "pose_blueprint",
        "identity_preservation",
        "deformation_map",
        "brand_attachment",
        "target_pose_compliance",
        "brand_integration_compliance",
        "identity_corrections",
        "pose_corrections",
        "brand_corrections",
        "revision_instruction",
    ):
        assert field in javascript

    assert "姿势与视角变化本身不扣身份分" in javascript
    assert "Identity Preservation 不等于 Pose Preservation" in javascript
