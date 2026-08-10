"""One-step-per-rerun workflow engine with JSON checkpoints.

`run_next_step` executes one agent only.  `run_until_complete` exists for tests and
CLI smoke checks; the Streamlit UI should persist `checkpoint()` after every step
and advance from a fresh rerun.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Literal, Mapping
from uuid import uuid4

from pydantic import ValidationError

from app.agents import BaseAgent, build_default_agents
from app.agents.base import AgentContext
from app.errors import (
    CheckpointError,
    GuardianRejectedError,
    ImageGenerationError,
    InvalidWorkflowTransitionError,
)
from app.schemas import (
    AgentExecutionResult,
    AgentStatus,
    GuardianResult,
    GuardianVerdict,
    IPIdentityGrammar,
    InputAssets,
    UserIntent,
    WorkflowSnapshot,
    WorkflowStatus,
    utc_now,
)

from .events import WorkflowEventType, make_event
from .graph import AgentNames, WorkflowGraph


MAX_GUARDIAN_RETRIES = 2
CURRENT_WORKFLOW_SCHEMA_VERSION = 2


class WorkflowEngine:
    """Deterministic orchestration over the static twelve-agent graph."""

    def __init__(
        self,
        *,
        ai_provider: Any | None = None,
        image_provider: Any | None = None,
        search_provider: Any | None = None,
        agents: Mapping[str, BaseAgent[Any]] | None = None,
        graph: WorkflowGraph | None = None,
        checkpoint: WorkflowSnapshot | Mapping[str, Any] | None = None,
        max_guardian_retries: int = MAX_GUARDIAN_RETRIES,
    ) -> None:
        if max_guardian_retries < 0:
            raise ValueError("max_guardian_retries cannot be negative")
        self.graph = graph or WorkflowGraph()
        self.ai_provider = ai_provider
        self.image_provider = image_provider
        self.search_provider = search_provider
        self.agents: dict[str, BaseAgent[Any]] = dict(
            agents
            or build_default_agents(
                ai_provider=ai_provider,
                image_provider=image_provider,
                search_provider=search_provider,
            )
        )
        missing = set(self.graph.order) - set(self.agents)
        extra = set(self.agents) - set(self.graph.order)
        if missing or extra:
            raise ValueError(
                f"Agent registry must exactly match graph; missing={sorted(missing)}, "
                f"extra={sorted(extra)}"
            )
        self._max_guardian_retries = max_guardian_retries
        self._snapshot: WorkflowSnapshot | None = None
        if checkpoint is not None:
            self.restore(checkpoint)

    @property
    def snapshot(self) -> WorkflowSnapshot | None:
        return self._snapshot.model_copy(deep=True) if self._snapshot is not None else None

    def start(
        self,
        *,
        input_assets: InputAssets | Mapping[str, Any],
        user_intent: UserIntent | Mapping[str, Any],
        run_id: str | None = None,
    ) -> WorkflowSnapshot:
        """Create a new running checkpoint without executing an agent."""

        assets = (
            input_assets
            if isinstance(input_assets, InputAssets)
            else InputAssets.model_validate(input_assets)
        )
        intent = (
            user_intent
            if isinstance(user_intent, UserIntent)
            else UserIntent.model_validate(user_intent)
        )
        now = utc_now()
        snapshot = WorkflowSnapshot(
            workflow_schema_version=CURRENT_WORKFLOW_SCHEMA_VERSION,
            revision=1,
            run_id=run_id or f"run-{uuid4().hex}",
            status=WorkflowStatus.RUNNING,
            input_assets=assets,
            user_intent=intent,
            current_agent=self.graph.order[0],
            pending_agents=list(self.graph.order),
            max_guardian_retries=self._max_guardian_retries,
            started_at=now,
            updated_at=now,
        )
        snapshot.events.append(
            make_event(
                WorkflowEventType.WORKFLOW_STARTED,
                run_id=snapshot.run_id,
                revision=snapshot.revision,
                pending_agents=list(snapshot.pending_agents),
            ).checkpoint_dict()
        )
        self._snapshot = snapshot
        return snapshot.model_copy(deep=True)

    def restore(
        self, checkpoint: WorkflowSnapshot | Mapping[str, Any]
    ) -> WorkflowSnapshot:
        """Restore and validate a snapshot created after any prior workflow step."""

        try:
            restored = (
                checkpoint.model_copy(deep=True)
                if isinstance(checkpoint, WorkflowSnapshot)
                else WorkflowSnapshot.model_validate(checkpoint)
            )
        except ValidationError as exc:
            raise CheckpointError("Workflow checkpoint validation failed") from exc

        known = set(self.graph.order)
        referenced = (
            set(restored.pending_agents)
            | set(restored.completed_agents)
            | set(restored.outputs)
        )
        unknown = referenced - known
        if unknown:
            raise CheckpointError(
                "Workflow checkpoint references unknown agents",
                context={"unknown_agents": sorted(unknown)},
            )
        if restored.workflow_schema_version < CURRENT_WORKFLOW_SCHEMA_VERSION:
            self._upgrade_legacy_checkpoint_for_execution(restored)
        if restored.max_guardian_retries != self._max_guardian_retries:
            # The checkpoint owns the run's cost bound; restoring cannot silently
            # increase or decrease it because a new process used another default.
            self._max_guardian_retries = restored.max_guardian_retries
        # Restore is deliberately idempotent: recreating the engine during a
        # Streamlit rerun must not generate a new UI revision or audit event.
        self._snapshot = restored
        return restored.model_copy(deep=True)

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: WorkflowSnapshot | Mapping[str, Any],
        **kwargs: Any,
    ) -> "WorkflowEngine":
        return cls(checkpoint=checkpoint, **kwargs)

    def checkpoint(self) -> dict[str, Any]:
        if self._snapshot is None:
            raise CheckpointError("Workflow has not been started")
        return self._snapshot.model_dump(mode="json")

    def run_next_step(
        self,
        checkpoint: WorkflowSnapshot | Mapping[str, Any] | None = None,
    ) -> WorkflowSnapshot:
        """Execute one pending agent and return the resulting checkpoint."""

        if checkpoint is not None:
            self.restore(checkpoint)
        snapshot = self._require_snapshot()
        if snapshot.status == WorkflowStatus.COMPLETED:
            return snapshot.model_copy(deep=True)
        if snapshot.status == WorkflowStatus.FAILED:
            raise InvalidWorkflowTransitionError(
                "Failed workflow must retry its current agent before advancing",
                context={"failed_agent": snapshot.failed_agent},
            )
        if snapshot.status not in {WorkflowStatus.READY, WorkflowStatus.RUNNING}:
            raise InvalidWorkflowTransitionError(
                f"Cannot advance workflow in state {snapshot.status.value}"
            )
        if not snapshot.pending_agents:
            self._complete_workflow(snapshot)
            self._bump_revision(snapshot)
            return snapshot.model_copy(deep=True)

        agent_name = snapshot.pending_agents.pop(0)
        if not self.graph.dependencies_satisfied(agent_name, snapshot.completed_agents):
            # Restore the queue before surfacing a checkpoint-safe transition error.
            snapshot.pending_agents.insert(0, agent_name)
            raise InvalidWorkflowTransitionError(
                f"Dependencies are not satisfied for {agent_name}",
                context={
                    "required": list(self.graph.requirements_for(agent_name)),
                    "completed": list(snapshot.completed_agents),
                },
            )
        try:
            self._validate_business_gate(snapshot, agent_name)
        except Exception:
            snapshot.pending_agents.insert(0, agent_name)
            raise

        agent = self.agents[agent_name]
        attempt = sum(
            1 for record in snapshot.execution_records if record.agent_name == agent_name
        )
        context = AgentContext(
            run_id=snapshot.run_id,
            input_assets=snapshot.input_assets,
            user_intent=snapshot.user_intent,
            outputs=snapshot.outputs,
            guardian_retries=snapshot.guardian_retries,
            agent_retry_count=attempt,
            ai_provider=self.ai_provider,
            image_provider=self.image_provider,
            search_provider=self.search_provider,
        )
        snapshot.status = WorkflowStatus.RUNNING
        snapshot.current_agent = agent_name
        snapshot.failed_agent = None
        snapshot.error = None
        snapshot.updated_at = utc_now()
        snapshot.events.append(
            make_event(
                WorkflowEventType.AGENT_STARTED,
                run_id=snapshot.run_id,
                agent_name=agent_name,
                retry_count=attempt,
            ).checkpoint_dict()
        )

        started_at = utc_now()
        started_clock = perf_counter()
        try:
            input_summary = agent.input_summary(context)
            execution = agent.run(context)
        except Exception as exc:
            duration_ms = max(0, round((perf_counter() - started_clock) * 1000))
            error_message = f"{type(exc).__name__}: {exc}"
            retryable = bool(
                getattr(exc, "retryable", isinstance(exc, ImageGenerationError))
            )
            execution = AgentExecutionResult(
                status=AgentStatus.FAILED,
                agent_name=agent_name,
                input_summary=locals().get("input_summary", "Input summary unavailable"),
                decision_summary="Agent execution failed before producing a decision.",
                evidence=[],
                output={},
                output_summary="No output produced.",
                warnings=[],
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=utc_now(),
                error=error_message,
                retryable=retryable,
                retry_count=attempt,
                prompt_id=agent.prompt_id,
                prompt_version=agent.prompt_version,
                prompt_hash=agent.prompt_hash,
                model_route=agent.model_route,
                model=agent.model,
                responsibility=agent.responsibility,
                handoff=agent.handoff,
            )
            snapshot.execution_records.append(execution)
            snapshot.failed_agent = agent_name
            snapshot.error = error_message
            snapshot.status = WorkflowStatus.FAILED
            snapshot.updated_at = utc_now()
            snapshot.events.append(
                make_event(
                    WorkflowEventType.AGENT_FAILED,
                    run_id=snapshot.run_id,
                    agent_name=agent_name,
                    error_type=type(exc).__name__,
                    retryable=retryable,
                    retry_count=attempt,
                ).checkpoint_dict()
            )
            self._bump_revision(snapshot)
            return snapshot.model_copy(deep=True)

        snapshot.execution_records.append(execution)
        snapshot.outputs[agent_name] = execution.output
        if agent_name not in snapshot.completed_agents:
            snapshot.completed_agents.append(agent_name)
            snapshot.completed_agents.sort(key=self.graph.order.index)
        snapshot.last_completed_agent = agent_name
        snapshot.updated_at = utc_now()
        snapshot.events.append(
            make_event(
                WorkflowEventType.AGENT_COMPLETED,
                run_id=snapshot.run_id,
                agent_name=agent_name,
                duration_ms=execution.duration_ms,
                retry_count=attempt,
            ).checkpoint_dict()
        )

        if agent_name == AgentNames.IP_GUARDIAN:
            self._apply_guardian_transition(snapshot)
        if snapshot.status != WorkflowStatus.FAILED:
            snapshot.current_agent = (
                snapshot.pending_agents[0] if snapshot.pending_agents else None
            )
            if not snapshot.pending_agents:
                self._complete_workflow(snapshot)
        self._bump_revision(snapshot)
        return snapshot.model_copy(deep=True)

    def retry_current_agent(self) -> WorkflowSnapshot:
        """Requeue only the failed agent; successful dependencies remain checkpointed."""

        snapshot = self._require_snapshot()
        if snapshot.status != WorkflowStatus.FAILED or not snapshot.failed_agent:
            raise InvalidWorkflowTransitionError("No failed agent is available to retry")
        failed_agent = snapshot.failed_agent
        if (
            failed_agent == AgentNames.IP_GUARDIAN
            and snapshot.guardian_retries >= snapshot.max_guardian_retries
        ):
            raise GuardianRejectedError(
                "Guardian automatic retry limit is exhausted",
                context={
                    "guardian_retries": snapshot.guardian_retries,
                    "max_guardian_retries": snapshot.max_guardian_retries,
                },
            )
        if failed_agent not in snapshot.pending_agents:
            snapshot.pending_agents.insert(0, failed_agent)
        snapshot.status = WorkflowStatus.RUNNING
        snapshot.error = None
        snapshot.failed_agent = None
        snapshot.current_agent = failed_agent
        snapshot.updated_at = utc_now()
        snapshot.events.append(
            make_event(
                WorkflowEventType.AGENT_RETRY_REQUESTED,
                run_id=snapshot.run_id,
                agent_name=failed_agent,
            ).checkpoint_dict()
        )
        self._bump_revision(snapshot)
        return snapshot.model_copy(deep=True)

    def invalidate(
        self,
        change: Literal["user_intent", "ip_asset", "brand_asset"],
        *,
        new_input_assets: InputAssets | Mapping[str, Any] | None = None,
        new_user_intent: UserIntent | Mapping[str, Any] | None = None,
    ) -> WorkflowSnapshot:
        """Invalidate only nodes whose inputs transitively changed.

        The operation is safe on running, failed, and completed checkpoints. It
        preserves the unaffected branch, removes stale agent records/outputs, and
        rebuilds the queue in the graph's canonical order.
        """

        snapshot = self._require_snapshot()
        roots = {
            "user_intent": AgentNames.CREATIVE_BRIEF,
            "ip_asset": AgentNames.IP_PREPARATION,
            "brand_asset": AgentNames.BRAND_INTELLIGENCE,
        }
        if change not in roots:
            raise ValueError(f"Unsupported invalidation change: {change}")
        if change == "user_intent":
            if new_input_assets is not None:
                raise ValueError("user_intent invalidation cannot replace input assets")
            if new_user_intent is not None:
                snapshot.user_intent = self._merge_user_intent(
                    snapshot.user_intent, new_user_intent
                )
        else:
            if new_user_intent is not None:
                raise ValueError(f"{change} invalidation cannot replace user intent")
            if new_input_assets is not None:
                replacement = self._merge_input_assets(
                    snapshot.input_assets, new_input_assets
                )
                self._validate_asset_replacement_scope(
                    change=change,
                    current=snapshot.input_assets,
                    replacement=replacement,
                )
                snapshot.input_assets = replacement

        affected_order = self.graph.descendants_of(roots[change])
        affected = set(affected_order)
        # Leave terminal-state invariants before rebuilding pending work.
        snapshot.status = WorkflowStatus.RUNNING
        snapshot.completed_agents = [
            agent
            for agent in self.graph.order
            if agent in snapshot.completed_agents and agent not in affected
        ]
        snapshot.outputs = {
            agent: output
            for agent, output in snapshot.outputs.items()
            if agent not in affected
        }
        snapshot.execution_records = [
            record
            for record in snapshot.execution_records
            if record.agent_name not in affected
        ]
        snapshot.pending_agents = [
            agent for agent in self.graph.order if agent not in snapshot.completed_agents
        ]
        snapshot.guardian_retries = 0
        snapshot.failed_agent = None
        snapshot.error = None
        snapshot.completed_at = None
        snapshot.current_agent = (
            snapshot.pending_agents[0] if snapshot.pending_agents else None
        )
        snapshot.last_completed_agent = (
            snapshot.completed_agents[-1] if snapshot.completed_agents else None
        )
        self._bump_revision(snapshot)
        snapshot.events.append(
            make_event(
                WorkflowEventType.WORKFLOW_INVALIDATED,
                run_id=snapshot.run_id,
                change=change,
                invalidated_agents=list(affected_order),
                preserved_agents=list(snapshot.completed_agents),
                revision=snapshot.revision,
            ).checkpoint_dict()
        )
        return snapshot.model_copy(deep=True)

    def run_until_complete(self, *, max_steps: int = 64) -> WorkflowSnapshot:
        """Test/CLI convenience; production UI must use `run_next_step`."""

        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        snapshot = self._require_snapshot()
        steps = 0
        while snapshot.status not in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}:
            if steps >= max_steps:
                raise InvalidWorkflowTransitionError(
                    "Workflow exceeded the maximum step count",
                    context={"max_steps": max_steps},
                )
            snapshot = self.run_next_step()
            steps += 1
        return snapshot

    def latest_result(self, agent_name: str) -> AgentExecutionResult | None:
        snapshot = self._require_snapshot()
        for result in reversed(snapshot.execution_records):
            if result.agent_name == agent_name:
                return result.model_copy(deep=True)
        return None

    def _require_snapshot(self) -> WorkflowSnapshot:
        if self._snapshot is None:
            raise InvalidWorkflowTransitionError("Workflow has not been started")
        return self._snapshot

    @staticmethod
    def _merge_input_assets(
        current: InputAssets,
        replacement: InputAssets | Mapping[str, Any],
    ) -> InputAssets:
        if isinstance(replacement, InputAssets):
            return replacement.model_copy(deep=True)
        merged = current.model_dump(mode="python")
        merged.update(dict(replacement))
        return InputAssets.model_validate(merged)

    @staticmethod
    def _merge_user_intent(
        current: UserIntent,
        replacement: UserIntent | Mapping[str, Any],
    ) -> UserIntent:
        if isinstance(replacement, UserIntent):
            return replacement.model_copy(deep=True)
        merged = current.model_dump(mode="python")
        merged.update(dict(replacement))
        return UserIntent.model_validate(merged)

    @staticmethod
    def _validate_asset_replacement_scope(
        *,
        change: Literal["ip_asset", "brand_asset"],
        current: InputAssets,
        replacement: InputAssets,
    ) -> None:
        if change == "ip_asset":
            preserved = ("brand_image", "brand_filename", "brand_name")
        else:
            preserved = ("ip_image", "ip_filename")
        changed_out_of_scope = [
            field
            for field in preserved
            if getattr(current, field) != getattr(replacement, field)
        ]
        if changed_out_of_scope:
            raise ValueError(
                f"{change} replacement also changed preserved fields: "
                f"{changed_out_of_scope}"
            )

    @staticmethod
    def _bump_revision(snapshot: WorkflowSnapshot) -> None:
        snapshot.revision += 1
        snapshot.updated_at = utc_now()

    def _validate_business_gate(self, snapshot: WorkflowSnapshot, agent_name: str) -> None:
        if agent_name != AgentNames.RANKING:
            return
        try:
            guardian = GuardianResult.model_validate(snapshot.outputs[AgentNames.IP_GUARDIAN])
        except (KeyError, ValidationError) as exc:
            raise InvalidWorkflowTransitionError(
                "Ranking requires a valid Guardian result"
            ) from exc
        if guardian.verdict != GuardianVerdict.PASS:
            raise GuardianRejectedError(
                "Ranking cannot execute until Guardian PASS",
                context={"guardian_verdict": guardian.verdict.value},
            )
        if (
            snapshot.workflow_schema_version >= CURRENT_WORKFLOW_SCHEMA_VERSION
            and guardian.scoring_version != "pose_aware_grammar_v3"
        ):
            raise GuardianRejectedError(
                "Schema-v2 Ranking requires a pose-aware Guardian result",
                context={"scoring_version": guardian.scoring_version},
            )

    def _apply_guardian_transition(self, snapshot: WorkflowSnapshot) -> None:
        guardian = GuardianResult.model_validate(snapshot.outputs[AgentNames.IP_GUARDIAN])
        if guardian.verdict == GuardianVerdict.PASS:
            snapshot.events.append(
                make_event(
                    WorkflowEventType.GUARDIAN_PASSED,
                    run_id=snapshot.run_id,
                    agent_name=AgentNames.IP_GUARDIAN,
                    score=guardian.identity_score,
                    retry_count=snapshot.guardian_retries,
                ).checkpoint_dict()
            )
            return

        event_type = (
            WorkflowEventType.GUARDIAN_REJECTED
            if guardian.verdict == GuardianVerdict.REJECT
            else WorkflowEventType.GUARDIAN_REVISION_REQUESTED
        )
        snapshot.events.append(
            make_event(
                event_type,
                run_id=snapshot.run_id,
                agent_name=AgentNames.IP_GUARDIAN,
                score=guardian.identity_score,
                retry_count=snapshot.guardian_retries,
                revision_instruction=guardian.revision_instruction,
            ).checkpoint_dict()
        )
        if snapshot.guardian_retries >= snapshot.max_guardian_retries:
            snapshot.failed_agent = AgentNames.IP_GUARDIAN
            snapshot.error = (
                f"Guardian {guardian.verdict.value} after "
                f"{snapshot.max_guardian_retries} automatic regeneration retries"
            )
            snapshot.status = WorkflowStatus.FAILED
            return

        snapshot.guardian_retries += 1
        # Ranking and packaging remain queued behind a fresh generation + review.
        remainder = [
            name
            for name in snapshot.pending_agents
            if name not in {AgentNames.FUSION_GENERATION, AgentNames.IP_GUARDIAN}
        ]
        snapshot.pending_agents[:] = [
            AgentNames.FUSION_GENERATION,
            AgentNames.IP_GUARDIAN,
            *remainder,
        ]

    def _complete_workflow(self, snapshot: WorkflowSnapshot) -> None:
        missing = set(self.graph.order) - set(snapshot.completed_agents)
        if missing:
            snapshot.error = f"Workflow queue ended before agents completed: {sorted(missing)}"
            snapshot.status = WorkflowStatus.FAILED
            return
        snapshot.current_agent = None
        snapshot.completed_at = utc_now()
        snapshot.status = WorkflowStatus.COMPLETED
        snapshot.updated_at = snapshot.completed_at
        snapshot.events.append(
            make_event(
                WorkflowEventType.WORKFLOW_COMPLETED,
                run_id=snapshot.run_id,
                guardian_retries=snapshot.guardian_retries,
                execution_count=len(snapshot.execution_records),
            ).checkpoint_dict()
        )

    def _upgrade_legacy_checkpoint_for_execution(
        self, snapshot: WorkflowSnapshot
    ) -> None:
        """Migrate a schema-v1 checkpoint in memory without fabricating results."""

        # Leave terminal invariants before rebuilding the canonical pending
        # queue or assigning schema v2 under validate_assignment.
        snapshot.status = WorkflowStatus.RUNNING
        snapshot.completed_at = None
        affected: set[str] = set()
        ip_output = snapshot.outputs.get(AgentNames.IP_INTELLIGENCE)
        has_native_grammar = False
        if isinstance(ip_output, Mapping):
            try:
                grammar = IPIdentityGrammar.model_validate(
                    ip_output.get("identity_grammar")
                )
            except (TypeError, ValueError):
                pass
            else:
                has_native_grammar = not any(
                    "compatibility projection" in item.casefold()
                    for item in grammar.unknowns
                )
        if (
            AgentNames.IP_INTELLIGENCE in snapshot.completed_agents
            and not has_native_grammar
        ):
            affected.update(self.graph.descendants_of(AgentNames.IP_INTELLIGENCE))

        brand_output = snapshot.outputs.get(AgentNames.BRAND_FEATURE)
        has_native_affordances = False
        if isinstance(brand_output, Mapping):
            features = brand_output.get("features")
            has_native_affordances = bool(
                isinstance(features, list)
                and features
                and all(
                    isinstance(feature, Mapping)
                    and bool(feature.get("integration_affordances"))
                    for feature in features
                )
            )
        if AgentNames.BRAND_FEATURE in snapshot.completed_agents and not has_native_affordances:
            affected.update(self.graph.descendants_of(AgentNames.BRAND_FEATURE))

        if not affected and AgentNames.IP_ADAPTATION not in snapshot.outputs:
            affected.update(self.graph.descendants_of(AgentNames.IP_ADAPTATION))

        snapshot.outputs = {
            agent: output
            for agent, output in snapshot.outputs.items()
            if agent not in affected
        }
        snapshot.execution_records = [
            record
            for record in snapshot.execution_records
            if record.agent_name not in affected
        ]
        snapshot.completed_agents = [
            agent
            for agent in self.graph.order
            if agent in snapshot.completed_agents and agent not in affected
        ]
        snapshot.pending_agents = [
            agent for agent in self.graph.order if agent not in snapshot.completed_agents
        ]
        snapshot.workflow_schema_version = CURRENT_WORKFLOW_SCHEMA_VERSION
        snapshot.compatibility_warnings = list(
            dict.fromkeys(
                [
                    *snapshot.compatibility_warnings,
                    "legacy_workflow_schema_v1_migrated_for_execution",
                    "legacy_outputs_invalidated_without_fabricating_ip_adaptation",
                ]
            )
        )
        snapshot.failed_agent = None
        snapshot.error = None
        snapshot.guardian_retries = 0
        snapshot.current_agent = snapshot.pending_agents[0] if snapshot.pending_agents else None
        snapshot.last_completed_agent = (
            snapshot.completed_agents[-1] if snapshot.completed_agents else None
        )
        snapshot.events.append(
            make_event(
                WorkflowEventType.WORKFLOW_INVALIDATED,
                run_id=snapshot.run_id,
                change="workflow_schema_upgrade_v1_to_v2",
                invalidated_agents=[agent for agent in self.graph.order if agent in affected],
                preserved_agents=list(snapshot.completed_agents),
                workflow_schema_version=CURRENT_WORKFLOW_SCHEMA_VERSION,
            ).checkpoint_dict()
        )
