from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.ranking import RankingAgent
from app.errors import GuardianRejectedError
from app.schemas import (
    GuardianResult,
    GuardianVerdict,
    InputAssets,
    RANKING_WEIGHTS,
    RankingResult,
    UserIntent,
)
from app.workflow.engine import WorkflowEngine
from app.workflow.graph import AgentNames


def completed_snapshot():
    engine = WorkflowEngine()
    engine.start(
        input_assets=InputAssets(ip_image="ip.png", brand_image="brand.png"),
        user_intent=UserIntent(selected_goals=["服装融合"], goal_text="保留IP身份"),
        run_id="ranking-test",
    )
    return engine.run_until_complete()


def test_ranking_weights_and_reasons_are_complete() -> None:
    snapshot = completed_snapshot()
    ranking = RankingResult.model_validate(snapshot.outputs[AgentNames.RANKING])
    guardian = GuardianResult.model_validate(snapshot.outputs[AgentNames.IP_GUARDIAN])

    assert sum(RANKING_WEIGHTS.values()) == pytest.approx(1.0)
    assert set(ranking.score_breakdown) == set(RANKING_WEIGHTS)
    assert set(ranking.score_reasons) == set(RANKING_WEIGHTS)
    assert all(ranking.score_reasons.values())
    assert ranking.score_breakdown["ip_identity_consistency"] == guardian.identity_score
    expected = round(
        sum(
            ranking.score_breakdown[key] * weight
            for key, weight in RANKING_WEIGHTS.items()
        ),
        2,
    )
    assert ranking.total_score == expected


def test_ranking_agent_rejects_non_pass_guardian_candidate() -> None:
    snapshot = completed_snapshot()
    non_pass = GuardianResult(
        candidate_id=snapshot.outputs[AgentNames.FUSION_GENERATION]["candidate_id"],
        score=80,
        verdict=GuardianVerdict.REVISE,
        checks={"ip_silhouette": 80},
        findings=["revision required"],
        intent_constraints_met=True,
        revision_instruction="Restore the original head silhouette.",
    )
    outputs = dict(snapshot.outputs)
    outputs[AgentNames.IP_GUARDIAN] = non_pass.model_dump(mode="json")
    context = AgentContext(
        run_id=snapshot.run_id,
        input_assets=snapshot.input_assets,
        user_intent=snapshot.user_intent,
        outputs=outputs,
    )

    with pytest.raises(GuardianRejectedError):
        RankingAgent().process(context)
