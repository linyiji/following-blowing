"""Streamlit entry point for the AI IP × Brand workflow application."""

from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from app.config import APP_NAME, apply_runtime_provider_config, load_settings
from app.controller import ApplicationController
from app.health import AppBootstrap
from app.settings import (
    APISettingsService,
    ApiSettings,
    ProviderConnectionTester,
    RuntimeProviderConfig,
)
from app.schemas import ALLOWED_GOALS, WorkflowSnapshot
from app.state import (
    COMPONENT_KEY,
    component_defaults,
    consume_event,
    ensure_ui_state,
)
from app.ui.component import TRIGGER_KEYS, render_component


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_SAFE_RUN_ID = re.compile(r"^run[-_][A-Za-z0-9_-]{8,80}$")
_API_SERVICE_SESSION_KEY = "_following_blowing_api_settings_service"


st.set_page_config(
    page_title=APP_NAME,
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(
    """
    <style>
      [data-testid="stHeader"], [data-testid="stToolbar"], footer {display:none!important}
      [data-testid="stMainBlockContainer"] {max-width:none!important;padding:0!important}
      .stApp {background:#f5f6fb}
    </style>
    """,
    unsafe_allow_html=True,
)


def _streamlit_secrets() -> Mapping[str, Any]:
    try:
        return dict(st.secrets)
    except (FileNotFoundError, RuntimeError):
        return {}


def _component_value(result: Any, name: str) -> Any:
    if result is None:
        return None
    if isinstance(result, Mapping):
        return result.get(name)
    return getattr(result, name, None)


def _decode_upload(payload: Mapping[str, Any]) -> tuple[bytes, str]:
    data_url = str(payload.get("data_url") or "")
    if not data_url.startswith("data:") or ";base64," not in data_url:
        raise ValueError("上传图片缺少有效的数据内容")
    header, encoded = data_url.split(",", 1)
    mime = header[5:].split(";", 1)[0].lower()
    if mime not in {
        "",
        "application/octet-stream",
        "image/png",
        "image/jpeg",
        "image/webp",
    }:
        raise ValueError("仅支持 PNG、JPEG 和 WebP 图片")
    if len(encoded) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 8:
        raise ValueError(f"图片不能超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("上传图片编码无效") from exc
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"图片不能超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
    return data, mime or "application/octet-stream"


def _notification(ui: dict[str, Any], message: str, *, level: str = "info") -> None:
    counter = int(ui.get("notification_counter", 0)) + 1
    ui["notification_counter"] = counter
    ui["notification"] = {
        "event_id": f"backend-{counter}",
        "message": message,
        "level": level,
    }


def _browser_error(exc: Exception) -> str:
    """Return a bounded message without credentials or machine-local paths."""

    if isinstance(exc, FileNotFoundError):
        return "所需文件或 Workflow 运行记录不存在"
    if isinstance(exc, OSError):
        return "本地存储操作失败，请稍后重试"
    message = str(exc)
    message = re.sub(
        r"(?i)(api[_-]?key|authorization|password|secret|access[_-]?token)"
        r"\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        message,
    )
    message = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", message)
    message = re.sub(
        r"(?<![:/\w])/(?:[^/\s'\"<>]+/)*[^/\s'\"<>]*",
        "[local-path]",
        message,
    )
    return message[:500] or "操作未完成，请稍后重试"


def _query_run_id() -> str | None:
    try:
        value = st.query_params.get("run")
    except (AttributeError, KeyError, RuntimeError):
        return None
    if isinstance(value, (list, tuple)):
        value = value[-1] if value else None
    if value in (None, ""):
        return None
    run_id = str(value)
    if not _SAFE_RUN_ID.fullmatch(run_id):
        try:
            del st.query_params["run"]
        except (AttributeError, KeyError, RuntimeError):
            pass
        return None
    return run_id


def _set_query_run(run_id: str | None) -> None:
    try:
        if run_id:
            st.query_params["run"] = run_id
        elif "run" in st.query_params:
            del st.query_params["run"]
    except (AttributeError, KeyError, RuntimeError):
        pass


def _api_settings_service() -> APISettingsService:
    """Keep Session Only credentials alive across Streamlit reruns."""

    existing = st.session_state.get(_API_SERVICE_SESSION_KEY)
    if isinstance(existing, APISettingsService):
        return existing
    service = APISettingsService()
    st.session_state[_API_SERVICE_SESSION_KEY] = service
    return service


def _api_form_settings(payload: Mapping[str, Any]) -> ApiSettings:
    """Validate a one-time settings trigger while dropping event metadata."""

    current = api_settings_service.load()
    allowed = {
        "preset",
        "provider",
        "base_url",
        "model_fast",
        "model_main",
        "image_model",
        "fast_timeout",
        "main_timeout",
        "image_timeout",
        "timeouts",
    }
    values = {
        key: value
        for key, value in payload.items()
        if key in allowed and value not in (None, "")
    }
    provider = str(values.get("provider", current.provider)).strip().lower()
    if provider in {"openai compatible", "openai-compatible", "custom"}:
        values["provider"] = "openai_compatible"
    elif provider in {"openai", "teamorouter", "teamo"}:
        values["provider"] = current.provider if provider in {"teamorouter", "teamo"} else "openai"

    preset = str(values.get("preset", current.preset)).strip().lower()
    if preset in {"teamorouter", "teamo", "teamo-router"}:
        values.update(
            preset="teamorouter",
            base_url="https://api.teamorouter.com/v1",
            model_fast="gpt-5.6-luna",
            model_main="gpt-5.6-terra",
            image_model="gpt-image-2",
        )
    elif preset:
        values["preset"] = "custom"

    baseline = current.model_dump(mode="json")
    baseline.update(values)
    return api_settings_service._normalize_settings(baseline)


def _ephemeral_runtime_config(
    form: ApiSettings,
    supplied_key: str | None,
) -> RuntimeProviderConfig:
    """Build a test-only runtime config without persisting the supplied key."""

    key = supplied_key.strip() if supplied_key and supplied_key.strip() else None
    if key is None:
        key = api_settings_service.credential_store.get_secret()
    from pydantic import SecretStr

    return RuntimeProviderConfig(
        provider=form.provider,
        base_url=form.base_url,
        model_fast=form.model_fast,
        model_main=form.model_main,
        image_model=form.image_model,
        fast_timeout=form.fast_timeout,
        main_timeout=form.main_timeout,
        image_timeout=form.image_timeout,
        api_key=SecretStr(key) if key else None,
        credential_backend=(
            api_settings_service.credential_status().backend if key else "none"
        ),
    )


api_settings_service = _api_settings_service()
base_settings = load_settings(secrets=_streamlit_secrets())
api_settings_view = api_settings_service.public_view()
byok_runtime = api_settings_service.runtime_config()
if byok_runtime.has_api_key:
    settings = apply_runtime_provider_config(base_settings, byok_runtime)
    api_source = "byok"
    api_connected = True
else:
    settings = base_settings
    api_source = "admin" if not settings.demo_mode else "none"
    api_connected = bool(
        not settings.demo_mode
        and settings.multimodal.configured
        and settings.image.configured
    )

health = AppBootstrap(settings).run()
if health.status == "DEGRADED" and api_connected:
    st.error("应用启动检查未通过：" + "、".join(health.warnings))

controller = ApplicationController(settings)
demo_assets = controller.bootstrap_demo_assets()
ui = ensure_ui_state(st.session_state)
for key, default in {
    "api_settings_open": False,
    "api_connection_result": None,
    "api_settings_result": None,
    "api_demo_selected": False,
}.items():
    ui.setdefault(key, default)

# Explicit developer/admin Demo remains immediately usable. The formal BYOK
# first boot requires the user to deliberately choose Demo or configure an API.
demo_selected = bool(ui.get("api_demo_selected")) or bool(
    getattr(settings, "demo_explicit", bool(getattr(settings, "demo_mode", False)))
)
workflow_start_enabled = bool(api_connected or demo_selected)
api_readiness = {
    "status": "connected" if api_connected else "unconfigured",
    "source": api_source,
    "credential_configured": bool(api_settings_view.get("credential_configured")),
    "workflow_start_enabled": workflow_start_enabled,
    "demo_selected": demo_selected,
    "mode": "live" if api_connected else ("demo" if demo_selected else "unconfigured"),
    "services": {
        "fast": "READY" if api_connected else "NOT CONFIGURED",
        "main": "READY" if api_connected else "NOT CONFIGURED",
        "image": "READY" if api_connected else "NOT CONFIGURED",
        "search": "DEMO / MOCK",
    },
}


def _detach_competition_run(snapshot: WorkflowSnapshot | None) -> bool:
    """Keep an explicitly restored run immutable while preparing a fresh start."""

    if snapshot is None or not bool(getattr(settings, "competition_mode", False)):
        return False
    ui["run_id"] = None
    ui["selected_agent"] = None
    if ui.get("ai_suggestion_source_run_id") == snapshot.run_id:
        ui["ai_suggestion"] = None
        ui["ai_suggestion_adopted"] = False
        ui["ai_suggestion_source_run_id"] = None
        ui["ai_supplement_count"] = 0
    _set_query_run(None)
    _clear_download_state()
    return True


def _safe_asset_payload(asset_id: str | None) -> dict[str, Any] | None:
    try:
        return controller.asset_payload(asset_id)
    except (FileNotFoundError, ValueError):
        return None


def _snapshot_asset_id(snapshot: WorkflowSnapshot, role: str) -> str | None:
    metadata_key = "ip_asset_id" if role == "ip_image" else "brand_asset_id"
    value = snapshot.input_assets.metadata.get(metadata_key)
    if not value:
        try:
            value = controller.repository.get_run(snapshot.run_id).get(metadata_key)
        except (FileNotFoundError, ValueError):
            return None
    try:
        controller.assets.get(str(value))
    except (FileNotFoundError, ValueError):
        return None
    return str(value)


def _hydrate_run_before_component_normalization() -> None:
    """Recover the durable run and its UI inputs from the URL on a new session."""

    requested_run_id = _query_run_id()
    cached_run_id = str(ui.get("run_id") or "") or None
    if bool(getattr(settings, "competition_mode", False)):
        # Competition sessions never treat an old browser cache as a new live
        # run. Explicit ?run= remains the audit/recovery entry point.
        run_id = requested_run_id
        if run_id is None and cached_run_id is not None:
            ui.update(
                run_id=None,
                selected_agent=None,
                download_path=None,
                download_nonce=None,
                ai_suggestion=None,
                ai_suggestion_adopted=False,
                ai_suggestion_source_run_id=None,
                ai_supplement_count=0,
            )
            _set_query_run(None)
            return
    else:
        run_id = requested_run_id or cached_run_id
    if not run_id:
        return

    raw = st.session_state.get(COMPONENT_KEY, {})
    raw_page = raw.get("page_state") if isinstance(raw, Mapping) else None
    raw_page_run = raw_page.get("run_id") if isinstance(raw_page, Mapping) else None
    needs_run_hydration = (
        run_id != cached_run_id
        or not ui.get("ip_asset_id")
        or not ui.get("brand_asset_id")
    )
    needs_component_hydration = raw_page_run != run_id
    try:
        restored = controller.restore_snapshot(run_id)
    except (FileNotFoundError, ValueError):
        if cached_run_id == run_id:
            ui["run_id"] = None
        _set_query_run(None)
        return

    _set_query_run(run_id)
    if not (needs_run_hydration or needs_component_hydration):
        return

    ip_asset_id = _snapshot_asset_id(restored, "ip_image")
    brand_asset_id = _snapshot_asset_id(restored, "brand_image")
    suggestion = restored.user_intent.ai_suggestion
    suggestion_version = (
        suggestion.get("version", 0) if isinstance(suggestion, Mapping) else 0
    )
    restored_ui = dict(
        run_id=run_id,
        ip_asset_id=ip_asset_id,
        brand_asset_id=brand_asset_id,
        selected_goals=list(restored.user_intent.selected_goals),
        goal_text=restored.user_intent.goal_text,
        ai_suggestion=suggestion,
        ai_suggestion_adopted=restored.user_intent.ai_suggestion_adopted,
        ai_suggestion_source_run_id=(
            run_id if bool(getattr(settings, "competition_mode", False)) else None
        ),
        ai_supplement_count=max(
            int(ui.get("ai_supplement_count", 0)),
            int(suggestion_version or 0),
        ),
    )
    if needs_run_hydration:
        restored_ui.update(download_path=None, download_nonce=None)
    ui.update(restored_ui)
    if not isinstance(raw, dict):
        raw = {}
        st.session_state[COMPONENT_KEY] = raw
    raw.update(
        ip_image=_safe_asset_payload(ip_asset_id),
        brand_image=_safe_asset_payload(brand_asset_id),
        selected_goals=list(restored.user_intent.selected_goals),
        goal_text=restored.user_intent.goal_text,
        ai_suggestion=suggestion,
        page_state={
            "status": restored.status.value,
            "run_id": run_id,
            "revision": restored.revision,
            "active_agent": ui.get("selected_agent"),
        },
    )


def _restore_current_snapshot() -> WorkflowSnapshot | None:
    run_id = ui.get("run_id")
    if not run_id:
        return None
    try:
        return controller.restore_snapshot(str(run_id))
    except (FileNotFoundError, ValueError):
        ui["run_id"] = None
        _set_query_run(None)
        return None


def _clear_download_state() -> None:
    ui["download_path"] = None
    ui["download_nonce"] = None


def _normalize_asset_state(role: str, value: Any) -> bool:
    """Resolve a Component image state into a server-side asset reference."""

    if not isinstance(value, Mapping):
        return False
    current_key = "ip_asset_id" if role == "ip_image" else "brand_asset_id"
    asset_id = value.get("asset_id")
    try:
        if value.get("data_url"):
            binary, mime = _decode_upload(value)
            stored = controller.assets.ingest(
                binary,
                filename=str(value.get("filename") or f"{role}.png"),
                declared_mime=mime,
                source_type="upload",
            )
            asset_id = stored.asset_id
        if not asset_id:
            return False
        controller.assets.get(str(asset_id))
    except (OSError, TypeError, ValueError) as exc:
        _notification(
            ui,
            f"图片安全校验失败：{_browser_error(exc)}",
            level="error",
        )
        return False

    asset_id = str(asset_id)
    if ui.get(current_key) == asset_id:
        return False
    snapshot = _restore_current_snapshot()
    if snapshot is not None:
        if _detach_competition_run(snapshot):
            _notification(ui, "图片已更新；旧 Run 保持不变，Start 将创建全新比赛 Run")
        else:
            try:
                controller.invalidate_run(
                    snapshot.run_id,
                    "ip_asset" if role == "ip_image" else "brand_asset",
                    ip_asset_id=asset_id if role == "ip_image" else None,
                    brand_asset_id=asset_id if role == "brand_image" else None,
                )
                _notification(ui, "图片已更新，受影响的 Workflow 节点已失效并将重新执行")
            except Exception as exc:  # normalized for the browser; never includes secrets
                _notification(
                    ui,
                    f"Workflow 依赖失效处理失败：{_browser_error(exc)}",
                    level="error",
                )
                return False
    ui[current_key] = asset_id
    _clear_download_state()
    return True


def _normalize_component_state() -> None:
    raw = st.session_state.get(COMPONENT_KEY, {})
    if not isinstance(raw, dict):
        raw = {}
        st.session_state[COMPONENT_KEY] = raw

    _normalize_asset_state("ip_image", raw.get("ip_image"))
    _normalize_asset_state("brand_image", raw.get("brand_image"))

    selected = raw.get("selected_goals")
    selected_goals = (
        [str(item) for item in selected if str(item) in ALLOWED_GOALS]
        if isinstance(selected, list)
        else list(ui.get("selected_goals") or [])
    )
    selected_goals = list(dict.fromkeys(selected_goals))
    goal_text = str(raw.get("goal_text", ui.get("goal_text") or ""))
    suggestion = ui.get("ai_suggestion")
    intent_trigger_pending = any(
        raw.get(name) is not None
        for name in (
            "ai_supplement",
            "regenerate_suggestion",
            "clear_goal",
            "start_workflow",
        )
    )
    intent_changed = (
        selected_goals != list(ui.get("selected_goals") or [])
        or goal_text != str(ui.get("goal_text") or "")
    )
    page_state = raw.get("page_state")
    if isinstance(page_state, Mapping):
        ui["selected_agent"] = page_state.get("active_agent")

    if intent_changed and not intent_trigger_pending:
        snapshot = _restore_current_snapshot()
        if snapshot is not None:
            if _detach_competition_run(snapshot):
                _notification(ui, "目标已更新；旧 Run 保持不变，Start 将创建全新比赛 Run")
            else:
                try:
                    controller.invalidate_run(
                        snapshot.run_id,
                        "user_intent",
                        selected_goals=selected_goals,
                        goal_text=goal_text,
                        ai_suggestion=suggestion,
                        ai_suggestion_adopted=bool(ui.get("ai_suggestion_adopted")),
                    )
                    _notification(ui, "用户目标已更新，Creative Brief 及下游节点已失效")
                except Exception as exc:
                    _notification(
                        ui,
                        f"用户目标更新失败：{_browser_error(exc)}",
                        level="error",
                    )
                    selected_goals = list(ui.get("selected_goals") or [])
                    goal_text = str(ui.get("goal_text") or "")
                else:
                    _clear_download_state()

    ui["selected_goals"] = selected_goals
    ui["goal_text"] = goal_text

    # Replace upload Base64 immediately with a small browser-safe asset payload.
    raw.update(
        ip_image=_safe_asset_payload(ui.get("ip_asset_id")),
        brand_image=_safe_asset_payload(ui.get("brand_asset_id")),
        selected_goals=list(ui["selected_goals"]),
        goal_text=ui["goal_text"],
        ai_suggestion=ui.get("ai_suggestion"),
        page_state={
            "run_id": ui.get("run_id"),
            "active_agent": ui.get("selected_agent"),
        },
    )


_hydrate_run_before_component_normalization()
_normalize_component_state()
snapshot = _restore_current_snapshot()
public_snapshot = controller.public_snapshot(snapshot)
result_payload = controller.result_payload(snapshot)
if result_payload and result_payload.get("image_url"):
    result_payload["image_uri"] = result_payload["image_url"]


def _agent_details() -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    if snapshot is None:
        return details
    ranking_reasons = snapshot.outputs.get("Ranking Agent", {}).get("score_reasons", {})
    for record in snapshot.execution_records:
        detail = {
            "responsibility": record.responsibility,
            "inputs": record.input_summary,
            "decision_summary": record.decision_summary,
            "output": record.output_summary,
            "evidence": record.evidence,
            "warnings": record.warnings,
            "handoff": record.handoff,
        }
        if record.agent_name == "IP Intelligence Agent":
            detail["structured_output"] = {
                "identity_grammar": record.output.get("identity_grammar")
            }
        elif record.agent_name == "Fusion Decision Agent":
            detail["structured_output"] = {
                "fusion_relationship": record.output.get("fusion_relationship")
            }
        elif record.agent_name == "IP Adaptation Agent":
            detail["structured_output"] = record.output
        elif record.agent_name == "IP Guardian Agent":
            detail["structured_output"] = record.output
        if record.agent_name == "Ranking Agent":
            detail["score_reasons"] = ranking_reasons
        details[record.agent_name] = detail
    return details


download_payload: dict[str, Any] | None = None
download_path = ui.get("download_path")
if download_path and snapshot is not None and snapshot.status.value == "completed":
    try:
        archive = Path(str(download_path)).resolve()
        output_dir = (controller.repository.run_dir(snapshot.run_id) / "output").resolve()
        run_record = controller.repository.get_run(snapshot.run_id)
        if (
            archive.parent == output_dir
            and archive.name == run_record.get("design_package_id")
            and archive.is_file()
        ):
            download_payload = {
                "filename": archive.name,
                "mime_type": "application/zip",
                "data_base64": base64.b64encode(archive.read_bytes()).decode("ascii"),
                "event_id": ui.get("download_nonce") or archive.name,
                "auto_download": True,
            }
    except (FileNotFoundError, OSError, ValueError):
        _clear_download_state()

component_data: dict[str, Any] = {
    "app_name": getattr(settings, "app_name", APP_NAME),
    "demo_mode": demo_selected and not api_connected,
    "api_settings": {
        **api_settings_view,
        "open": bool(ui.get("api_settings_open")),
    },
    "api_readiness": api_readiness,
    "api_connection_result": ui.get("api_connection_result"),
    "api_settings_result": ui.get("api_settings_result"),
    "provider_status": (
        settings.public_status()
        if callable(getattr(settings, "public_status", None))
        else {"provider_mode": "demo" if settings.demo_mode else "unknown"}
    ),
    "max_upload_bytes": MAX_UPLOAD_BYTES,
    "ip_image": _safe_asset_payload(ui.get("ip_asset_id")),
    "brand_image": _safe_asset_payload(ui.get("brand_asset_id")),
    "selected_goals": list(ui.get("selected_goals") or []),
    "goal_text": str(ui.get("goal_text") or ""),
    "ai_suggestion": ui.get("ai_suggestion"),
    "state": component_defaults(st.session_state),
    "workflow_snapshot": public_snapshot,
    "page_state": public_snapshot or {"status": "ready", "run_id": None, "revision": 0},
    "result": result_payload,
    "final_result_image": result_payload.get("image_url") if result_payload else None,
    "agent_details": _agent_details(),
    "demo_assets": {
        "ip_image": controller.asset_payload(demo_assets["ip"].asset_id),
        "brand_image": controller.asset_payload(demo_assets["brand"].asset_id),
        "guardian_rejected": controller.assets.preview_data_uri(
            demo_assets["guardian_rejected"].asset_id
        ),
    },
    "download": download_payload,
    "notification": ui.get("notification"),
    "health": health.to_dict(),
}

component_result = render_component(
    component_data,
    defaults=component_defaults(st.session_state),
    key=COMPONENT_KEY,
)


def _trigger_payload(name: str) -> Any:
    return _component_value(component_result, name)


def _intent_from_trigger(payload: Any) -> None:
    if not isinstance(payload, Mapping):
        return
    selected = payload.get("selected_goals")
    if isinstance(selected, list):
        ui["selected_goals"] = [
            str(item) for item in selected if str(item) in ALLOWED_GOALS
        ]
    if "goal_text" in payload:
        ui["goal_text"] = str(payload.get("goal_text") or "")


def _current_snapshot_for_trigger(payload: Any) -> WorkflowSnapshot:
    current = _restore_current_snapshot()
    if current is None:
        raise ValueError("当前没有可操作的 Workflow")
    if isinstance(payload, Mapping):
        event_run_id = payload.get("run_id")
        if event_run_id not in (None, "", current.run_id):
            raise ValueError("该操作来自已过期的 Workflow")
        event_revision = payload.get("revision")
        if event_revision not in (None, ""):
            try:
                is_stale = int(event_revision) != current.revision
            except (TypeError, ValueError):
                is_stale = True
            if is_stale:
                raise ValueError("页面状态已更新，本次过期操作已忽略")
    return current


handled = False
for trigger_name in TRIGGER_KEYS:
    raw_payload = _trigger_payload(trigger_name)
    if raw_payload is None or not consume_event(st.session_state, raw_payload):
        continue
    payload = dict(raw_payload) if isinstance(raw_payload, Mapping) else raw_payload
    supplied_api_key: str | None = None
    if isinstance(payload, dict):
        candidate_key = payload.pop("credential_input", None)
        if candidate_key in (None, ""):
            candidate_key = payload.pop("api_key", None)
        supplied_api_key = str(candidate_key) if candidate_key not in (None, "") else None
    # Defense in depth: remove the one-time credential from any mutable result
    # object immediately after Python receives it. It is never copied to ui.
    if isinstance(raw_payload, dict):
        raw_payload.pop("credential_input", None)
        raw_payload.pop("api_key", None)
    try:
        if trigger_name == "open_api_settings":
            ui["api_settings_open"] = True
            ui["api_settings_result"] = None

        elif trigger_name == "close_api_settings":
            if isinstance(payload, Mapping) and bool(payload.get("use_demo")):
                ui["api_demo_selected"] = True
                ui["api_connection_result"] = None
                _notification(ui, "DEMO MODE 已启用；不会调用真实 API")
            ui["api_settings_open"] = False

        elif trigger_name == "test_api_connection":
            if not isinstance(payload, Mapping):
                raise ValueError("API 设置测试请求无效")
            form = _api_form_settings(payload)
            runtime = _ephemeral_runtime_config(form, supplied_api_key)
            tester = ProviderConnectionTester()
            result = (
                tester.test_image(runtime)
                if bool(payload.get("advanced_image_test"))
                else tester.test(runtime)
            )
            ui["api_connection_result"] = result.public_view()
            ui["api_settings_result"] = {
                "ok": result.ok,
                "message": result.message,
            }
            ui["api_settings_open"] = True

        elif trigger_name == "save_api_settings":
            if not isinstance(payload, Mapping):
                raise ValueError("API 设置保存请求无效")
            form = _api_form_settings(payload)
            saved = api_settings_service.save(
                form,
                api_key=supplied_api_key,
                persist_credential=True,
            )
            ui["api_demo_selected"] = False
            ui["api_settings_open"] = True
            ui["api_settings_result"] = {
                "ok": True,
                "message": (
                    "设置已保存到系统安全凭据存储。"
                    if saved.credential.persistent
                    else "设置已保存；API Key 仅在当前会话中使用。"
                ),
            }
            _notification(ui, "API 设置已保存")

        elif trigger_name == "delete_api_credentials":
            deleted = api_settings_service.delete_credential()
            ui["api_demo_selected"] = False
            ui["api_connection_result"] = None
            ui["api_settings_open"] = True
            ui["api_settings_result"] = {
                "ok": not deleted.configured,
                "message": "API 凭据已删除。请重新配置或选择 Demo Mode。",
            }
            _notification(ui, "API 凭据已从安全存储删除")

        elif trigger_name in {"ai_supplement", "regenerate_suggestion"}:
            if not workflow_start_enabled:
                raise ValueError("请先配置 API，或明确选择 Demo Mode")
            _intent_from_trigger(payload)
            count = int(ui.get("ai_supplement_count", 0)) + 1
            if count > settings.max_ai_supplement_retries:
                raise ValueError("本次会话的 AI 补充生成次数已达到上限")
            ui["ai_supplement_count"] = count
            new_suggestion = controller.create_ai_suggestion(
                selected_goals=ui["selected_goals"],
                goal_text=ui["goal_text"],
                version=count,
            )
            current = _restore_current_snapshot()
            intent_changed = current is not None and (
                list(current.user_intent.selected_goals)
                != list(ui.get("selected_goals") or [])
                or current.user_intent.goal_text != str(ui.get("goal_text") or "")
                or current.user_intent.ai_suggestion_adopted
            )
            if current is not None and intent_changed:
                if not _detach_competition_run(current):
                    _current_snapshot_for_trigger(payload)
                    controller.invalidate_run(
                        current.run_id,
                        "user_intent",
                        selected_goals=ui["selected_goals"],
                        goal_text=ui["goal_text"],
                        ai_suggestion=new_suggestion,
                        ai_suggestion_adopted=False,
                    )
                    _clear_download_state()
            ui["ai_suggestion"] = new_suggestion
            ui["ai_suggestion_adopted"] = False
            ui["ai_suggestion_source_run_id"] = None
            _notification(ui, f"AI 补充建议已生成 · v{count}")

        elif trigger_name == "adopt_suggestion":
            if not ui.get("ai_suggestion"):
                raise ValueError("请先生成 AI 补充建议")
            if (
                bool(getattr(settings, "competition_mode", False))
                and ui.get("ai_suggestion_source_run_id")
            ):
                raise ValueError("恢复 Run 的 AI 建议仅供审计，请在比赛 Run 前重新生成")
            current = _restore_current_snapshot()
            if current is not None:
                if not _detach_competition_run(current):
                    _current_snapshot_for_trigger(payload)
                    controller.invalidate_run(
                        current.run_id,
                        "user_intent",
                        selected_goals=ui["selected_goals"],
                        goal_text=ui["goal_text"],
                        ai_suggestion=ui["ai_suggestion"],
                        ai_suggestion_adopted=True,
                    )
                    _clear_download_state()
            ui["ai_suggestion_adopted"] = True
            _notification(ui, "AI 建议已采用；你的自由输入保持不变")

        elif trigger_name == "clear_goal":
            current = _restore_current_snapshot()
            if current is not None:
                if not _detach_competition_run(current):
                    _current_snapshot_for_trigger(payload)
                    controller.invalidate_run(
                        current.run_id,
                        "user_intent",
                        selected_goals=[],
                        goal_text="",
                        ai_suggestion=None,
                        ai_suggestion_adopted=False,
                    )
                    _clear_download_state()
            ui.update(
                selected_goals=[],
                goal_text="",
                ai_suggestion=None,
                ai_suggestion_adopted=False,
                ai_suggestion_source_run_id=None,
                ai_supplement_count=0,
            )
            _notification(ui, "用户目标已清空")

        elif trigger_name == "start_workflow":
            if not workflow_start_enabled:
                raise ValueError("请先配置 API，或明确选择 Demo Mode")
            _intent_from_trigger(payload)
            if not ui.get("ip_asset_id") or not ui.get("brand_asset_id"):
                raise ValueError("请先加载 IP 与品牌参考图")
            restored_suggestion = bool(
                getattr(settings, "competition_mode", False)
                and ui.get("ai_suggestion_source_run_id")
            )
            snapshot = controller.start_workflow(
                ip_asset_id=str(ui["ip_asset_id"]),
                brand_asset_id=str(ui["brand_asset_id"]),
                selected_goals=ui["selected_goals"],
                goal_text=ui["goal_text"],
                ai_suggestion=(None if restored_suggestion else ui.get("ai_suggestion")),
                ai_suggestion_adopted=(
                    False
                    if restored_suggestion
                    else bool(ui.get("ai_suggestion_adopted"))
                ),
            )
            if restored_suggestion:
                ui["ai_suggestion"] = None
                ui["ai_suggestion_adopted"] = False
            ui["ai_suggestion_source_run_id"] = None
            ui["run_id"] = snapshot.run_id
            _set_query_run(snapshot.run_id)
            _clear_download_state()
            ui["selected_agent"] = None
            _notification(ui, "AI Workflow 已启动")

        elif trigger_name == "advance_workflow":
            current = _current_snapshot_for_trigger(payload)
            snapshot = controller.advance_workflow(current.run_id)
            if snapshot.status.value == "completed":
                _notification(ui, "12 个 Agent 已全部完成，结果已输出")

        elif trigger_name == "retry_agent":
            current = _current_snapshot_for_trigger(payload)
            snapshot = controller.retry_current_agent(current.run_id)
            _notification(ui, f"正在重试 {snapshot.current_agent or '当前 Agent'}")

        elif trigger_name == "open_agent_detail":
            if isinstance(payload, Mapping):
                ui["selected_agent"] = payload.get("agent_name")

        elif trigger_name == "export_package":
            current = _current_snapshot_for_trigger(payload)
            archive = controller.export_design_package(current.run_id)
            ui["download_path"] = str(archive)
            ui["download_nonce"] = (
                payload.get("event_id") if isinstance(payload, Mapping) else archive.name
            )
            _notification(ui, "联名设计内容包已生成")

        handled = True
    except Exception as exc:  # show a browser-safe message without server traceback/secrets
        safe_error = _browser_error(exc)
        ui["last_error"] = safe_error
        _notification(ui, f"操作失败：{safe_error}", level="error")
        handled = True
    break

if handled:
    st.rerun()
