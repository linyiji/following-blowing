"""Streamlit Components v2 bridge for the AI IP × Brand workflow UI.

The visual source lives in three plain frontend files so it remains reviewable
against the original HTML demo.  Registration happens once, when this module is
imported; :func:`render_component` only mounts the registered renderer.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import streamlit as st


FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
COMPONENT_NAME = "ai_ip_brand_workflow"

STATE_KEYS: tuple[str, ...] = (
    "ip_image",
    "brand_image",
    "image_pair",
    "advance_request",
    "selected_goals",
    "goal_text",
    "ai_suggestion",
    "page_state",
)

TRIGGER_KEYS: tuple[str, ...] = (
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
)

DEFAULT_STATE: dict[str, Any] = {
    "ip_image": None,
    "brand_image": None,
    "image_pair": {"ip_image": None, "brand_image": None},
    "advance_request": None,
    "selected_goals": [],
    "goal_text": "",
    "ai_suggestion": None,
    "page_state": {},
}


def _read_frontend(name: str) -> str:
    return (FRONTEND_DIR / name).read_text(encoding="utf-8")


_component_renderer = st.components.v2.component(
    COMPONENT_NAME,
    html=_read_frontend("component.html"),
    css=_read_frontend("component.css"),
    js=_read_frontend("component.js"),
    isolate_styles=True,
)


def _empty_callback() -> None:
    """Declare a v2 value without imposing app-level callback behavior."""


def render_component(
    data: Mapping[str, Any] | None,
    defaults: Mapping[str, Any] | None = None,
    key: str = "ai_ip_brand_component",
) -> Any:
    """Mount the workflow component and return its bidirectional result.

    ``data`` is deliberately generic: the application may pass a serialized
    ``WorkflowSnapshot`` plus UI-specific fields without coupling this module to
    workflow services.  All documented state and trigger callbacks are mounted
    because Components v2 requires a callback for every value emitted by JS.
    """

    mounted_defaults = deepcopy(DEFAULT_STATE)
    if defaults:
        mounted_defaults.update(dict(defaults))

    value_names = set(STATE_KEYS) | set(TRIGGER_KEYS) | set(mounted_defaults)
    callbacks = {
        f"on_{name}_change": _empty_callback for name in sorted(value_names)
    }

    return _component_renderer(
        data=dict(data or {}),
        default=mounted_defaults,
        key=key,
        **callbacks,
    )


__all__ = [
    "COMPONENT_NAME",
    "DEFAULT_STATE",
    "STATE_KEYS",
    "TRIGGER_KEYS",
    "render_component",
]
