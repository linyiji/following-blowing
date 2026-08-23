from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from pathlib import Path
from typing import Any

from app.schemas import InputAssets, UserIntent
from app.state import COMPONENT_KEY, UI_STATE_KEY
from app.ui.component import TRIGGER_KEYS
from app.workflow.engine import WorkflowEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_save_settings_refreshes_modal_and_home_status_independently_from_test() -> None:
    source = (PROJECT_ROOT / "streamlit_app.py").read_text(encoding="utf-8")

    save_branch = source.split('elif trigger_name == "save_api_settings":', 1)[1].split(
        'elif trigger_name == "delete_api_credentials":', 1
    )[0]
    assert 'ui["api_settings_open"] = True' in save_branch
    assert 'ui["api_settings_force_close"] = False' in save_branch
    assert 'ui["api_connection_result"] = None' in save_branch
    assert "弹窗与主页服务状态已更新" in save_branch
    assert "consume_verified_credential" in save_branch
    assert "请先完成测试连接" in save_branch


def _snapshot():
    return WorkflowEngine().start(
        run_id="run_12345678",
        input_assets=InputAssets(
            ip_image="server-ip.png",
            brand_image="server-brand.png",
            metadata={
                "ip_asset_id": "asset_ip",
                "brand_asset_id": "asset_brand",
            },
        ),
        user_intent=UserIntent(
            selected_goals=["服装融合"],
            goal_text="保留用户原始表情",
            ai_suggestion={"version": 2, "items": ["a", "b", "c"]},
            ai_suggestion_adopted=True,
        ),
    )


def _load_entry(
    monkeypatch: Any,
    *,
    session_state: dict[str, Any],
    query_params: dict[str, Any],
    fail_invalidation: bool = False,
    competition_mode: bool = False,
    component_triggers: dict[str, Any] | None = None,
):
    snapshot = _snapshot()
    mounts: list[dict[str, Any]] = []

    streamlit = types.ModuleType("streamlit")
    streamlit.session_state = session_state
    streamlit.query_params = query_params
    streamlit.secrets = {}
    streamlit.set_page_config = lambda **kwargs: None
    streamlit.markdown = lambda *args, **kwargs: None
    streamlit.error = lambda *args, **kwargs: None
    streamlit.stop = lambda: None
    streamlit.rerun = lambda: None
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)

    import app.config as config_module
    import app.controller as controller_module
    import app.health as health_module
    import app.ui.component as component_module

    settings = types.SimpleNamespace(
        demo_mode=True,
        competition_mode=competition_mode,
        max_ai_supplement_retries=3,
    )
    monkeypatch.setattr(config_module, "load_settings", lambda **kwargs: settings)

    class FakeHealth:
        status = "DEMO_MODE"
        warnings: list[str] = []

        def to_dict(self):
            return {"status": self.status}

    class FakeBootstrap:
        def __init__(self, supplied_settings):
            assert supplied_settings is settings

        def run(self):
            return FakeHealth()

    monkeypatch.setattr(health_module, "AppBootstrap", FakeBootstrap)

    class FakeAssets:
        def get(self, asset_id: str):
            if asset_id not in {"asset_ip", "asset_brand", "asset_new"}:
                raise FileNotFoundError(asset_id)
            return types.SimpleNamespace(asset_id=asset_id)

        def preview_data_uri(self, asset_id: str):
            return f"data:image/png;base64,{asset_id}"

    class FakeRepository:
        def get_run(self, run_id: str):
            assert run_id == snapshot.run_id
            return {
                "ip_asset_id": "asset_ip",
                "brand_asset_id": "asset_brand",
                "design_package_id": None,
            }

        def run_dir(self, run_id: str):
            return PROJECT_ROOT / "data" / "runs" / run_id

    class FakeController:
        def __init__(self, supplied_settings):
            assert supplied_settings is settings
            self.assets = FakeAssets()
            self.repository = FakeRepository()

        def bootstrap_demo_assets(self):
            return {
                name: types.SimpleNamespace(asset_id=asset_id)
                for name, asset_id in {
                    "ip": "asset_ip",
                    "brand": "asset_brand",
                    "final": "asset_ip",
                    "guardian_rejected": "asset_brand",
                }.items()
            }

        def restore_snapshot(self, run_id: str):
            if run_id != snapshot.run_id:
                raise FileNotFoundError(run_id)
            return snapshot.model_copy(deep=True)

        def invalidate_run(self, *args, **kwargs):
            if fail_invalidation:
                raise OSError("/Users/service/private/checkpoint.json")
            return snapshot.model_copy(deep=True)

        def asset_payload(self, asset_id: str | None):
            if not asset_id:
                return None
            self.assets.get(asset_id)
            return {
                "asset_id": asset_id,
                "preview_url": f"data:image/png;base64,{asset_id}",
            }

        def public_snapshot(self, value):
            if value is None:
                return None
            return {
                "run_id": value.run_id,
                "revision": value.revision,
                "status": value.status.value,
                "current_agent": value.current_agent,
                "last_completed_agent": value.last_completed_agent,
                "pending_agents": list(value.pending_agents),
                "completed_agents": list(value.completed_agents),
                "execution_records": [],
                "guardian_retries": 0,
                "max_guardian_retries": 2,
                "failed_agent": None,
                "error": None,
            }

        def result_payload(self, value):
            del value
            return None

        def start_workflow(self, **kwargs):
            start_calls.append(kwargs)
            return snapshot.model_copy(deep=True)

    monkeypatch.setattr(controller_module, "ApplicationController", FakeController)

    start_calls: list[dict[str, Any]] = []

    def render_component(data, defaults, key):
        mounts.append({"data": data, "defaults": defaults, "key": key})
        values = {name: None for name in TRIGGER_KEYS}
        values.update(component_triggers or {})
        return values

    monkeypatch.setattr(component_module, "render_component", render_component)

    module_name = f"streamlit_entry_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(
        module_name, PROJECT_ROOT / "streamlit_app.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    module._test_start_calls = start_calls
    return module, mounts, snapshot


def test_query_run_restores_inputs_and_intent_before_component_mount(
    monkeypatch: Any,
) -> None:
    session: dict[str, Any] = {}
    _, mounts, snapshot = _load_entry(
        monkeypatch,
        session_state=session,
        query_params={"run": "run_12345678"},
    )

    ui = session[UI_STATE_KEY]
    assert ui["run_id"] == snapshot.run_id
    assert ui["ip_asset_id"] == "asset_ip"
    assert ui["brand_asset_id"] == "asset_brand"
    assert ui["selected_goals"] == ["服装融合"]
    assert ui["goal_text"] == "保留用户原始表情"
    assert ui["ai_suggestion_adopted"] is True
    assert session[COMPONENT_KEY]["page_state"]["run_id"] == snapshot.run_id
    assert mounts[0]["data"]["ip_image"]["asset_id"] == "asset_ip"
    assert mounts[0]["data"]["goal_text"] == "保留用户原始表情"


def test_competition_ignores_cached_run_without_explicit_query(
    monkeypatch: Any,
) -> None:
    session = {
        UI_STATE_KEY: {
            "run_id": "run_12345678",
            "ip_asset_id": "asset_ip",
            "brand_asset_id": "asset_brand",
            "selected_goals": ["服装融合"],
            "goal_text": "保留用户原始表情",
            "ai_suggestion": {"version": 2, "items": ["a", "b", "c"]},
            "ai_suggestion_adopted": True,
            "download_path": "/server/run/output/old.zip",
        },
        COMPONENT_KEY: {
            "ip_image": {"asset_id": "asset_ip"},
            "brand_image": {"asset_id": "asset_brand"},
            "selected_goals": ["服装融合"],
            "goal_text": "保留用户原始表情",
            "ai_suggestion": {"version": 2, "items": ["a", "b", "c"]},
            "page_state": {"run_id": "run_12345678", "active_agent": None},
        },
    }

    _, mounts, _ = _load_entry(
        monkeypatch,
        session_state=session,
        query_params={},
        competition_mode=True,
    )

    ui = session[UI_STATE_KEY]
    assert ui["run_id"] is None
    assert ui["ai_suggestion"] is None
    assert ui["ai_suggestion_adopted"] is False
    assert mounts[0]["data"]["workflow_snapshot"] is None
    assert mounts[0]["data"]["page_state"]["run_id"] is None


def test_competition_explicit_query_still_restores_as_audit_only(
    monkeypatch: Any,
) -> None:
    session: dict[str, Any] = {}

    _, mounts, snapshot = _load_entry(
        monkeypatch,
        session_state=session,
        query_params={"run": "run_12345678"},
        competition_mode=True,
    )

    ui = session[UI_STATE_KEY]
    assert ui["run_id"] == snapshot.run_id
    assert ui["ai_suggestion_source_run_id"] == snapshot.run_id
    assert mounts[0]["data"]["workflow_snapshot"]["run_id"] == snapshot.run_id


def test_noncompetition_mode_preserves_cached_run_restore(monkeypatch: Any) -> None:
    session = {
        UI_STATE_KEY: {
            "run_id": "run_12345678",
            "ip_asset_id": "asset_ip",
            "brand_asset_id": "asset_brand",
        },
        COMPONENT_KEY: {"page_state": {"run_id": None}},
    }

    _, mounts, snapshot = _load_entry(
        monkeypatch,
        session_state=session,
        query_params={},
        competition_mode=False,
    )

    assert session[UI_STATE_KEY]["run_id"] == snapshot.run_id
    assert mounts[0]["data"]["workflow_snapshot"]["run_id"] == snapshot.run_id


def test_competition_start_does_not_reuse_restored_ai_provider_output(
    monkeypatch: Any,
) -> None:
    session: dict[str, Any] = {}
    module, _, _ = _load_entry(
        monkeypatch,
        session_state=session,
        query_params={"run": "run_12345678"},
        competition_mode=True,
        component_triggers={
            "start_workflow": {
                "event_id": "competition-fresh-start",
                "selected_goals": ["服装融合"],
                "goal_text": "保留用户原始表情",
            }
        },
    )

    assert len(module._test_start_calls) == 1
    call = module._test_start_calls[0]
    assert call["ai_suggestion"] is None
    assert call["ai_suggestion_adopted"] is False


def test_failed_asset_invalidation_rolls_component_back_to_durable_asset(
    monkeypatch: Any,
) -> None:
    session = {
        UI_STATE_KEY: {
            "run_id": "run_12345678",
            "ip_asset_id": "asset_ip",
            "brand_asset_id": "asset_brand",
            "selected_goals": ["服装融合"],
            "goal_text": "保留用户原始表情",
        },
        COMPONENT_KEY: {
            "ip_image": {"asset_id": "asset_new"},
            "brand_image": {"asset_id": "asset_brand"},
            "selected_goals": ["服装融合"],
            "goal_text": "保留用户原始表情",
            "ai_suggestion": None,
            "page_state": {"run_id": "run_12345678", "active_agent": None},
        },
    }
    _, mounts, _ = _load_entry(
        monkeypatch,
        session_state=session,
        query_params={"run": "run_12345678"},
        fail_invalidation=True,
    )

    assert session[UI_STATE_KEY]["ip_asset_id"] == "asset_ip"
    assert session[COMPONENT_KEY]["ip_image"]["asset_id"] == "asset_ip"
    assert mounts[0]["data"]["ip_image"]["asset_id"] == "asset_ip"
    notification = session[UI_STATE_KEY]["notification"]
    assert "/Users/" not in notification["message"]


def test_component_remount_does_not_clear_prepared_download(monkeypatch: Any) -> None:
    session = {
        UI_STATE_KEY: {
            "run_id": "run_12345678",
            "ip_asset_id": "asset_ip",
            "brand_asset_id": "asset_brand",
            "selected_goals": ["服装融合"],
            "goal_text": "保留用户原始表情",
            "ai_suggestion": {"version": 2, "items": ["a", "b", "c"]},
            "ai_suggestion_adopted": True,
            "download_path": "/server/run/output/package.zip",
            "download_nonce": "export-1",
        },
        COMPONENT_KEY: {
            "ip_image": {"asset_id": "asset_ip"},
            "brand_image": {"asset_id": "asset_brand"},
            "selected_goals": ["服装融合"],
            "goal_text": "保留用户原始表情",
            "ai_suggestion": {"version": 2, "items": ["a", "b", "c"]},
            # Components may remount before its state callback mirrors the run.
            "page_state": {"run_id": None, "active_agent": None},
        },
    }

    _load_entry(
        monkeypatch,
        session_state=session,
        query_params={"run": "run_12345678"},
    )

    assert session[UI_STATE_KEY]["download_path"] == "/server/run/output/package.zip"
    assert session[UI_STATE_KEY]["download_nonce"] == "export-1"
    assert session[COMPONENT_KEY]["page_state"]["run_id"] == "run_12345678"
