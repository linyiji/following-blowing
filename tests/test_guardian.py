from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.ip_guardian import IPGuardianAgent
from app.errors import GuardianRejectedError
from app.schemas import (
    GuardianCheck,
    GuardianCheckSet,
    GuardianResult,
    GuardianVerdict,
    GuardianVisionAssessment,
    InputAssets,
    UserIntent,
    WorkflowStatus,
)
from app.workflow.engine import MAX_GUARDIAN_RETRIES, WorkflowEngine
from app.workflow.graph import AgentNames


def run_with_scores(scores: list[float]):
    engine = WorkflowEngine()
    engine.start(
        input_assets=InputAssets(ip_image="ip.png", brand_image="brand.png"),
        user_intent=UserIntent(metadata={"guardian_score_sequence": scores}),
        run_id="guardian-test",
    )
    return engine, engine.run_until_complete()


def guardian_outputs(snapshot) -> list[GuardianResult]:
    return [
        GuardianResult.model_validate(record.output)
        for record in snapshot.execution_records
        if record.agent_name == AgentNames.IP_GUARDIAN
    ]


def test_guardian_reject_revise_pass_loop_is_checkpointed() -> None:
    _, snapshot = run_with_scores([70, 80, 90])

    assert snapshot.status == WorkflowStatus.COMPLETED
    assert snapshot.guardian_retries == MAX_GUARDIAN_RETRIES
    assert [result.verdict for result in guardian_outputs(snapshot)] == [
        GuardianVerdict.REJECT,
        GuardianVerdict.REVISE,
        GuardianVerdict.PASS,
    ]
    generation_records = [
        record
        for record in snapshot.execution_records
        if record.agent_name == AgentNames.FUSION_GENERATION
    ]
    assert [record.retry_count for record in generation_records] == [0, 1, 2]
    assert all("guardian_metrics" not in record.output for record in generation_records)
    assert "Revision required:" not in generation_records[0].output["generation_prompt"]
    assert all(
        "Revision required:" in record.output["generation_prompt"]
        for record in generation_records[1:]
    )
    assert len(snapshot.execution_records) == 16


def test_guardian_stops_after_two_automatic_regenerations() -> None:
    engine, snapshot = run_with_scores([70, 70, 70])

    assert snapshot.status == WorkflowStatus.FAILED
    assert snapshot.failed_agent == AgentNames.IP_GUARDIAN
    assert snapshot.guardian_retries == MAX_GUARDIAN_RETRIES
    assert AgentNames.RANKING not in snapshot.outputs
    assert AgentNames.DESIGN_PACKAGE not in snapshot.outputs
    assert len(guardian_outputs(snapshot)) == 3
    with pytest.raises(GuardianRejectedError):
        engine.retry_current_agent()


def test_guardian_retry_loop_resumes_from_checkpoint() -> None:
    engine = WorkflowEngine()
    engine.start(
        input_assets=InputAssets(ip_image="ip.png", brand_image="brand.png"),
        user_intent=UserIntent(metadata={"guardian_score_sequence": [70, 90]}),
        run_id="guardian-restore-test",
    )
    snapshot = None
    for _ in range(10):
        snapshot = engine.run_next_step()

    assert snapshot is not None
    assert snapshot.last_completed_agent == AgentNames.IP_GUARDIAN
    assert snapshot.guardian_retries == 1
    assert snapshot.pending_agents[0:2] == [
        AgentNames.FUSION_GENERATION,
        AgentNames.IP_GUARDIAN,
    ]

    restored = WorkflowEngine.from_checkpoint(engine.checkpoint())
    completed = restored.run_until_complete()
    assert completed.status == WorkflowStatus.COMPLETED
    assert [result.verdict for result in guardian_outputs(completed)] == [
        GuardianVerdict.REJECT,
        GuardianVerdict.PASS,
    ]


def test_guardian_uses_terra_dual_image_checks_but_python_decides_score() -> None:
    _, baseline = run_with_scores([90])
    values = {
        "original_ip_recognition": 100,
        "identity_anchor_consistency": 80,
        "facial_relationship_consistency": 40,
        "structural_grammar_consistency": 70,
        "proportion_signature_consistency": 30,
        "line_style_grammar_consistency": 20,
        "valid_pose_deformation": 90,
        "target_pose_compliance": 90,
        "user_intent_compliance": 10,
        "brand_integration_compliance": 80,
    }
    assessment = GuardianVisionAssessment(
        verdict=GuardianVerdict.PASS,
        checks=GuardianCheckSet(
            **{
                key: GuardianCheck(score=score, reason=f"visual evidence for {key}")
                for key, score in values.items()
            }
        ),
        major_differences=["head and face changed"],
        preserve=["original head"],
        change_only=["clothing"],
        revision_instruction="Restore the original head and facial geometry.",
    )

    class RecordingProvider:
        def __init__(self) -> None:
            self.call = None

        def analyze_multimodal(self, **kwargs):
            self.call = kwargs
            return assessment

    provider = RecordingProvider()
    context = AgentContext(
        run_id=baseline.run_id,
        input_assets=baseline.input_assets,
        user_intent=baseline.user_intent,
        outputs=baseline.outputs,
    )
    result = IPGuardianAgent(ai_provider=provider).process(context).output
    candidate = baseline.outputs[AgentNames.FUSION_GENERATION]

    assert provider.call["images"] == [
        baseline.input_assets.ip_image,
        candidate["image_uri"],
    ]
    assert provider.call["model_role"] == "main"
    assert "Image 1" in provider.call["prompt"]
    assert "Image 2" in provider.call["prompt"]
    assert result.identity_score == 67.0
    assert result.score == 67.0
    assert result.verdict == GuardianVerdict.REJECT
    assert result.intent_constraints_met is False
    assert result.target_pose_compliance == 90
    assert set(result.check_reasons) == set(values)
