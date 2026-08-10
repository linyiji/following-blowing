"""Structured events emitted by each workflow transition."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import utc_now


class WorkflowEventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    GUARDIAN_REJECTED = "guardian_rejected"
    GUARDIAN_REVISION_REQUESTED = "guardian_revision_requested"
    GUARDIAN_PASSED = "guardian_passed"
    AGENT_RETRY_REQUESTED = "agent_retry_requested"
    WORKFLOW_INVALIDATED = "workflow_invalidated"
    CHECKPOINT_RESTORED = "checkpoint_restored"
    WORKFLOW_COMPLETED = "workflow_completed"


class WorkflowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: WorkflowEventType
    run_id: str
    agent_name: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)

    def checkpoint_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def make_event(
    event_type: WorkflowEventType,
    *,
    run_id: str,
    agent_name: str | None = None,
    **payload: Any,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_type=event_type,
        run_id=run_id,
        agent_name=agent_name,
        payload=payload,
    )
