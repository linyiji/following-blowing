from __future__ import annotations

from typing import Any

from app.errors import (
    AgentExecutionError as WorkflowAgentExecutionError,
    GuardianRejectedError as WorkflowGuardianRejectedError,
    ImageGenerationError as WorkflowImageGenerationError,
    ProviderError as WorkflowProviderError,
    SearchError as WorkflowSearchError,
)


class AgentExecutionError(WorkflowAgentExecutionError):
    def __init__(self, message: str, *, agent_name: str = "unknown") -> None:
        super().__init__(agent_name, message)


class _GovernedProviderError:
    request_id: str | None
    retryable: bool

    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        retryable: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        merged_context = dict(context or {})
        if request_id:
            merged_context["request_id"] = request_id
        super().__init__(message, context=merged_context)  # type: ignore[misc]
        self.request_id = request_id
        self.retryable = retryable


class ProviderError(_GovernedProviderError, WorkflowProviderError):
    pass


class ImageGenerationError(_GovernedProviderError, WorkflowImageGenerationError):
    pass


class GuardianRejectedError(WorkflowGuardianRejectedError):
    pass


class SearchError(_GovernedProviderError, WorkflowSearchError):
    pass


__all__ = [
    "AgentExecutionError",
    "GuardianRejectedError",
    "ImageGenerationError",
    "ProviderError",
    "SearchError",
]
