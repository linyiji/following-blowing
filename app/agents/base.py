"""Common execution wrapper and context passed to deterministic agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Generic, Mapping, TypeVar

from pydantic import BaseModel

from app.config import MODEL_FAST, MODEL_MAIN, IMAGE_MODEL
from app.prompt_loader import PromptSpec, load_prompt
from app.schemas import (
    AgentExecutionResult,
    AgentStatus,
    InputAssets,
    UserIntent,
    utc_now,
)


OutputT = TypeVar("OutputT", bound=BaseModel)


def checkpoint_value(value: Any) -> Any:
    """Recursively convert agent/provider values into checkpoint-safe data."""

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): checkpoint_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [checkpoint_value(item) for item in value]
    if isinstance(value, bytes):
        # Providers should normally persist binary results.  This marker prevents
        # accidental binary data from leaking into a Streamlit component payload.
        return {"binary_bytes": len(value)}
    return value


@dataclass(frozen=True)
class AgentContext:
    run_id: str
    input_assets: InputAssets
    user_intent: UserIntent
    outputs: Mapping[str, Mapping[str, Any]]
    guardian_retries: int = 0
    agent_retry_count: int = 0
    ai_provider: Any | None = None
    image_provider: Any | None = None
    search_provider: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def require_output(self, agent_name: str, model_type: type[OutputT]) -> OutputT:
        try:
            raw = self.outputs[agent_name]
        except KeyError as exc:
            raise ValueError(f"Required output is unavailable: {agent_name}") from exc
        return model_type.model_validate(raw)


@dataclass(frozen=True)
class AgentDecision(Generic[OutputT]):
    output: OutputT
    decision_summary: str
    output_summary: str
    evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class BaseAgent(ABC, Generic[OutputT]):
    name: str
    responsibility: str
    handoff: str
    prompt_id: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    model_route: str | None = None
    model: str | None = None

    def __init__(self, *, ai_provider: Any | None = None) -> None:
        self.ai_provider = ai_provider
        self._prompt_spec: PromptSpec | None = None
        if self.prompt_id:
            spec = load_prompt(self.prompt_id)
            self._prompt_spec = spec
            self.prompt_version = spec.version
            self.prompt_hash = spec.prompt_hash
            self.model_route = spec.model_route
            self.model = {
                "fast": MODEL_FAST,
                "main": MODEL_MAIN,
                "image": IMAGE_MODEL,
            }[spec.model_route]

    @property
    def prompt_text(self) -> str:
        if self._prompt_spec is None:
            raise RuntimeError(f"{self.name} does not declare a versioned prompt")
        return self._prompt_spec.body

    @abstractmethod
    def input_summary(self, context: AgentContext) -> str:
        """Return a short, auditable summary without embedding source images."""

    @abstractmethod
    def process(self, context: AgentContext) -> AgentDecision[OutputT]:
        """Execute the agent's bounded business decision."""

    def run(self, context: AgentContext) -> AgentExecutionResult:
        started_at = utc_now()
        started_clock = perf_counter()
        decision = self.process(context)
        completed_at = utc_now()
        duration_ms = max(0, round((perf_counter() - started_clock) * 1000))
        output = checkpoint_value(decision.output)
        if not isinstance(output, dict):
            raise TypeError(f"{self.name} output must serialize to an object")
        return AgentExecutionResult(
            status=AgentStatus.COMPLETED,
            agent_name=self.name,
            input_summary=self.input_summary(context),
            decision_summary=decision.decision_summary,
            evidence=list(decision.evidence),
            output=output,
            output_summary=decision.output_summary,
            warnings=list(decision.warnings),
            duration_ms=duration_ms,
            started_at=started_at,
            completed_at=completed_at,
            retry_count=context.agent_retry_count,
            prompt_id=self.prompt_id,
            prompt_version=self.prompt_version,
            prompt_hash=self.prompt_hash,
            model_route=self.model_route,
            model=self.model,
            responsibility=self.responsibility,
            handoff=self.handoff,
        )
