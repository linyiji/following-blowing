from __future__ import annotations

from pathlib import Path

from app.schemas import InputAssets, UserIntent, WorkflowStatus
from app.workflow.engine import WorkflowEngine
from app.workflow.graph import AGENT_ORDER, AgentNames


class RecordingImageProvider:
    def __init__(self, output: str = "/tmp/demo-result.png") -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    def edit_with_reference(self, **kwargs: object) -> Path:
        self.calls.append(kwargs)
        return Path(self.output)


def make_engine(**kwargs: object) -> WorkflowEngine:
    return WorkflowEngine(**kwargs)


def start(engine: WorkflowEngine, *, metadata: dict | None = None):
    return engine.start(
        input_assets=InputAssets(
            ip_image="assets/demo/ip.png",
            brand_image="assets/demo/brand.png",
        ),
        user_intent=UserIntent(
            selected_goals=["服装融合", "品牌配色"],
            goal_text="保留线条小狗的表情",
            metadata=metadata or {},
        ),
        run_id="run-test",
    )


def test_each_advance_executes_exactly_one_agent_in_order() -> None:
    assert AGENT_ORDER == (
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
    )
    engine = make_engine()
    snapshot = start(engine)

    for index, expected_agent in enumerate(AGENT_ORDER, start=1):
        snapshot = engine.run_next_step()
        assert snapshot.last_completed_agent == expected_agent
        assert len(snapshot.execution_records) == index

    assert snapshot.status == WorkflowStatus.COMPLETED
    assert snapshot.completed_agents == list(AGENT_ORDER)


def test_checkpoint_round_trip_resumes_without_reexecuting_completed_agents() -> None:
    engine = make_engine()
    start(engine)
    first = engine.run_next_step()
    checkpoint = engine.checkpoint()

    restored = WorkflowEngine.from_checkpoint(checkpoint)
    second = restored.run_next_step()

    assert first.completed_agents == [AgentNames.IP_PREPARATION]
    assert second.completed_agents == [
        AgentNames.IP_PREPARATION,
        AgentNames.IP_INTELLIGENCE,
    ]
    assert [record.agent_name for record in second.execution_records] == list(AGENT_ORDER[:2])


def test_demo_workflow_uses_image_provider_and_completes() -> None:
    image_provider = RecordingImageProvider()
    engine = make_engine(image_provider=image_provider)
    start(engine)

    snapshot = engine.run_until_complete()

    assert snapshot.status == WorkflowStatus.COMPLETED
    assert len(image_provider.calls) == 1
    candidate = snapshot.outputs[AgentNames.FUSION_GENERATION]
    assert candidate["image_uri"] == image_provider.output
    assert candidate["metadata"]["image_provider_used"] is True
    assert AgentNames.DESIGN_PACKAGE in snapshot.outputs


def test_no_provider_configuration_still_completes_in_demo_fallback() -> None:
    engine = make_engine()
    start(engine)

    snapshot = engine.run_until_complete()

    assert snapshot.status == WorkflowStatus.COMPLETED
    candidate = snapshot.outputs[AgentNames.FUSION_GENERATION]
    assert candidate["image_uri"] == "assets/demo/final_result.png"
    assert candidate["metadata"]["image_provider_used"] is False


def test_checkpoint_revision_is_monotonic_and_restore_is_idempotent() -> None:
    engine = make_engine()
    started = start(engine)
    assert started.revision == 1

    first = engine.run_next_step()
    assert first.revision == 2
    checkpoint = engine.checkpoint()
    restored = WorkflowEngine.from_checkpoint(checkpoint)
    assert restored.snapshot is not None
    assert restored.snapshot.revision == first.revision

    retried_process = restored.run_next_step()
    assert retried_process.revision == first.revision + 1


def test_prompt_backed_agents_record_prompt_version() -> None:
    engine = make_engine()
    start(engine)
    snapshot = engine.run_until_complete()
    prompt_backed = {
        AgentNames.IP_INTELLIGENCE,
        AgentNames.BRAND_INTELLIGENCE,
        AgentNames.BRAND_COLLABORATION,
        AgentNames.BRAND_FEATURE,
        AgentNames.CREATIVE_BRIEF,
        AgentNames.FUSION_DECISION,
        AgentNames.IP_ADAPTATION,
        AgentNames.FUSION_GENERATION,
        AgentNames.IP_GUARDIAN,
        AgentNames.RANKING,
        AgentNames.DESIGN_PACKAGE,
    }

    for record in snapshot.execution_records:
        if record.agent_name in prompt_backed:
            assert record.prompt_version
        else:
            assert record.prompt_version is None


def test_user_intent_invalidation_preserves_both_completed_branches() -> None:
    engine = make_engine()
    start(engine, metadata={"guardian_score_sequence": [70, 80, 90]})
    completed = engine.run_until_complete()
    assert completed.guardian_retries == 2

    invalidated = engine.invalidate(
        "user_intent",
        new_user_intent={
            "selected_goals": ["场景融合"],
            "goal_text": "新的用户目标",
            "ai_suggestion": None,
            "ai_suggestion_adopted": False,
            "metadata": {},
        },
    )

    assert invalidated.revision == completed.revision + 1
    assert invalidated.status == WorkflowStatus.RUNNING
    assert invalidated.completed_at is None
    assert invalidated.guardian_retries == 0
    assert invalidated.completed_agents == list(AGENT_ORDER[:5])
    assert invalidated.pending_agents == list(AGENT_ORDER[5:])
    assert set(invalidated.outputs) == set(AGENT_ORDER[:5])
    assert [record.agent_name for record in invalidated.execution_records] == list(
        AGENT_ORDER[:5]
    )
    assert invalidated.user_intent.goal_text == "新的用户目标"


def test_ip_asset_invalidation_preserves_brand_branch() -> None:
    engine = make_engine()
    start(engine)
    engine.run_until_complete()

    invalidated = engine.invalidate(
        "ip_asset",
        new_input_assets={"ip_image": "assets/demo/new-ip.png", "ip_filename": "new-ip.png"},
    )
    preserved = [
        AgentNames.BRAND_INTELLIGENCE,
        AgentNames.BRAND_COLLABORATION,
        AgentNames.BRAND_FEATURE,
    ]
    expected_pending = [
        AgentNames.IP_PREPARATION,
        AgentNames.IP_INTELLIGENCE,
        *AGENT_ORDER[5:],
    ]

    assert invalidated.input_assets.ip_image == "assets/demo/new-ip.png"
    assert invalidated.completed_agents == preserved
    assert set(invalidated.outputs) == set(preserved)
    assert invalidated.pending_agents == expected_pending
    rerun = engine.run_until_complete()
    assert rerun.status == WorkflowStatus.COMPLETED
    assert rerun.completed_agents == list(AGENT_ORDER)


def test_brand_asset_invalidation_preserves_ip_branch() -> None:
    engine = make_engine()
    start(engine)
    engine.run_until_complete()

    invalidated = engine.invalidate(
        "brand_asset",
        new_input_assets={
            "brand_image": "assets/demo/new-brand.png",
            "brand_filename": "new-brand.png",
            "brand_name": "New Brand",
        },
    )

    assert invalidated.input_assets.brand_name == "New Brand"
    assert invalidated.completed_agents == list(AGENT_ORDER[:2])
    assert set(invalidated.outputs) == set(AGENT_ORDER[:2])
    assert invalidated.pending_agents == list(AGENT_ORDER[2:])
    assert [record.agent_name for record in invalidated.execution_records] == list(
        AGENT_ORDER[:2]
    )
