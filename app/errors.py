"""Domain errors for workflow, provider, search, and image failures."""

from __future__ import annotations

from typing import Any


class WorkflowError(RuntimeError):
    """Base class carrying browser-safe diagnostic context."""

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error_type": type(self).__name__, "message": str(self), "context": self.context}


class AgentExecutionError(WorkflowError):
    def __init__(self, agent_name: str, message: str) -> None:
        super().__init__(message, context={"agent_name": agent_name})
        self.agent_name = agent_name


class ProviderError(WorkflowError):
    pass


class ImageGenerationError(ProviderError):
    pass


class GuardianRejectedError(WorkflowError):
    pass


class SearchError(ProviderError):
    pass


class InvalidWorkflowTransitionError(WorkflowError):
    pass


class CheckpointError(WorkflowError):
    pass
