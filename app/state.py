"""Browser-session UI cache helpers.

Durable workflow state belongs to ``LocalRunRepository``.  This module keeps
only lightweight browser/session references and mirrors the six Component v2
state values so Python can fully hydrate the UI after a rerun.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from copy import deepcopy
from typing import Any


COMPONENT_KEY = "ai_ip_brand_component"
UI_STATE_KEY = "ai_ip_brand_ui"
MAX_PROCESSED_EVENTS = 128

COMPONENT_STATE_DEFAULTS: dict[str, Any] = {
    "ip_image": None,
    "brand_image": None,
    "image_pair": {"ip_image": None, "brand_image": None},
    "advance_request": None,
    "selected_goals": [],
    "goal_text": "",
    "ai_suggestion": None,
    "page_state": "READY",
}

UI_DEFAULTS: dict[str, Any] = {
    "run_id": None,
    "ip_asset_id": None,
    "brand_asset_id": None,
    "selected_goals": [],
    "goal_text": "",
    "ai_suggestion": None,
    "ai_suggestion_adopted": False,
    "ai_suggestion_source_run_id": None,
    "ai_supplement_count": 0,
    "selected_agent": None,
    "processed_event_ids": [],
    "download_path": None,
    "download_nonce": None,
    "last_error": None,
}


def ensure_ui_state(session: MutableMapping[str, Any]) -> dict[str, Any]:
    """Initialize and return the lightweight UI cache."""

    current = session.setdefault(UI_STATE_KEY, {})
    if not isinstance(current, dict):
        current = {}
        session[UI_STATE_KEY] = current
    for key, value in UI_DEFAULTS.items():
        current.setdefault(key, deepcopy(value))

    component = session.setdefault(COMPONENT_KEY, {})
    if not isinstance(component, dict):
        component = {}
        session[COMPONENT_KEY] = component
    for key, value in COMPONENT_STATE_DEFAULTS.items():
        component.setdefault(key, deepcopy(value))
    return current


def update_component_state(
    session: MutableMapping[str, Any],
    **values: Any,
) -> dict[str, Any]:
    """Programmatically update only declared Component v2 state values."""

    ensure_ui_state(session)
    component = session[COMPONENT_KEY]
    unknown = set(values) - set(COMPONENT_STATE_DEFAULTS)
    if unknown:
        raise KeyError(f"Unknown component state values: {sorted(unknown)}")
    for key, value in values.items():
        component[key] = deepcopy(value)
    return component


def component_defaults(session: MutableMapping[str, Any]) -> dict[str, Any]:
    ensure_ui_state(session)
    return {
        key: deepcopy(session[COMPONENT_KEY].get(key, default))
        for key, default in COMPONENT_STATE_DEFAULTS.items()
    }


def event_identifier(payload: Any) -> str | None:
    """Extract the frontend's unique event id without trusting other fields."""

    if not isinstance(payload, dict):
        return None
    value = payload.get("event_id")
    return str(value) if value not in (None, "") else None


def consume_event(session: MutableMapping[str, Any], payload: Any) -> bool:
    """Return ``True`` once for each versioned trigger envelope."""

    ui = ensure_ui_state(session)
    identifier = event_identifier(payload)
    if identifier is None:
        # Trigger values are transient in Components v2, so scalar legacy
        # payloads can safely be handled once in their single rerun.
        return payload is not None
    processed: list[str] = ui["processed_event_ids"]
    if identifier in processed:
        return False
    processed.append(identifier)
    if len(processed) > MAX_PROCESSED_EVENTS:
        del processed[:-MAX_PROCESSED_EVENTS]
    return True


def reset_intent(session: MutableMapping[str, Any]) -> None:
    ui = ensure_ui_state(session)
    ui.update(
        selected_goals=[],
        goal_text="",
        ai_suggestion=None,
        ai_suggestion_adopted=False,
        ai_suggestion_source_run_id=None,
        ai_supplement_count=0,
    )
    update_component_state(
        session,
        selected_goals=[],
        goal_text="",
        ai_suggestion=None,
    )


__all__ = [
    "COMPONENT_KEY",
    "COMPONENT_STATE_DEFAULTS",
    "UI_STATE_KEY",
    "component_defaults",
    "consume_event",
    "ensure_ui_state",
    "event_identifier",
    "reset_intent",
    "update_component_state",
]
