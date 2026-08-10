from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.schemas import (
    AgentExecutionResult,
    AgentStatus,
    CandidateDesign,
    GUARDIAN_IDENTITY_WEIGHTS,
    GuardianResult,
    GuardianVerdict,
    IPDNA,
    RANKING_WEIGHTS,
    RankingResult,
    UserIntent,
    calculate_guardian_identity_score,
    guardian_verdict_for_score,
    utc_now,
)


def test_user_intent_enforces_options_and_priority() -> None:
    intent = UserIntent(
        selected_goals=["服装融合", "品牌配色", "服装融合"],
        goal_text="  保留原角色表情  ",
        ai_suggestion={"idea": "增加欢乐餐场景"},
        ai_suggestion_adopted=True,
    )

    assert intent.selected_goals == ["服装融合", "品牌配色"]
    assert intent.prioritized_constraints() == [
        "保留原角色表情",
        "服装融合",
        "品牌配色",
        "idea: 增加欢乐餐场景",
    ]

    with pytest.raises(ValidationError):
        UserIntent(selected_goals=["不存在的选项"])


@pytest.mark.parametrize(
    ("score", "verdict"),
    [
        (0, GuardianVerdict.REJECT),
        (74.99, GuardianVerdict.REJECT),
        (75, GuardianVerdict.REVISE),
        (84.99, GuardianVerdict.REVISE),
        (85, GuardianVerdict.PASS),
        (100, GuardianVerdict.PASS),
    ],
)
def test_guardian_threshold_boundaries(score: float, verdict: GuardianVerdict) -> None:
    assert guardian_verdict_for_score(score) == verdict


def test_guardian_schema_rejects_inconsistent_verdict() -> None:
    with pytest.raises(ValidationError):
        GuardianResult(
            candidate_id="candidate-1",
            score=80,
            verdict=GuardianVerdict.PASS,
            checks={"ip_silhouette": 80},
            findings=["needs revision"],
            intent_constraints_met=True,
        )


def test_guardian_identity_score_uses_fixed_python_weights() -> None:
    assert GUARDIAN_IDENTITY_WEIGHTS == {
        "original_ip_recognition": 25,
        "identity_anchor_consistency": 20,
        "facial_relationship_consistency": 15,
        "structural_grammar_consistency": 15,
        "proportion_signature_consistency": 10,
        "line_style_grammar_consistency": 10,
        "valid_pose_deformation": 5,
    }
    assert sum(GUARDIAN_IDENTITY_WEIGHTS.values()) == 100
    checks = {
        "original_ip_recognition": 100,
        "identity_anchor_consistency": 80,
        "facial_relationship_consistency": 40,
        "structural_grammar_consistency": 70,
        "proportion_signature_consistency": 30,
        "line_style_grammar_consistency": 20,
        "valid_pose_deformation": 90,
        "target_pose_compliance": 0,
        "user_intent_compliance": 0,
        "brand_integration_compliance": 0,
    }
    assert calculate_guardian_identity_score(checks) == 67.0

    with pytest.raises(ValueError, match="missing"):
        calculate_guardian_identity_score({"identity_anchor_consistency": 80})


def test_old_candidate_metrics_parse_but_never_serialize() -> None:
    candidate = CandidateDesign(
        candidate_id="candidate-old",
        image_uri="candidate.png",
        theme_name="Legacy",
        fusion_logic="Legacy checkpoint",
        design_tags=[],
        generation_prompt="legacy",
        guardian_metrics={"ip_silhouette": 99},
    )
    assert candidate.guardian_metrics == {"ip_silhouette": 99}
    assert "guardian_metrics" not in candidate.model_dump(mode="json")

    legacy_ip_dna = IPDNA.model_validate(
        {
            "silhouette": "legacy silhouette",
            "head_structure": "legacy head",
            "ear_structure": "legacy ears",
            "facial_relationships": "legacy face",
            "body_proportions": "legacy proportions",
            "line_language": "legacy line",
            "recognition_markers": ["legacy marker"],
            "confidence": 0.9,
        }
    )
    assert legacy_ip_dna.eye_structure == "legacy face"
    assert legacy_ip_dna.immutable_features == ["legacy marker"]

    legacy_guardian = GuardianResult.model_validate(
        {
            "candidate_id": "candidate-old",
            "score": 90,
            "verdict": "PASS",
            "checks": {"ip_silhouette": 90},
            "findings": ["legacy finding"],
            "intent_constraints_met": True,
        }
    )
    assert legacy_guardian.identity_score == legacy_guardian.score == 90
    assert legacy_guardian.scoring_version == "legacy_v1"


def test_ranking_schema_calculates_exact_weighted_total() -> None:
    assert RANKING_WEIGHTS == {
        "user_goal_match": 0.25,
        "ip_identity_consistency": 0.25,
        "brand_recognition": 0.15,
        "fusion_naturalness": 0.15,
        "commercial_value": 0.10,
        "historical_collaboration_reference": 0.05,
        "innovation": 0.05,
    }
    assert sum(RANKING_WEIGHTS.values()) == pytest.approx(1.0)
    scores = {key: 80.0 + index for index, key in enumerate(RANKING_WEIGHTS)}
    reasons = {key: f"Reason for {key}" for key in RANKING_WEIGHTS}
    result = RankingResult.from_scores(
        candidate_id="candidate-1",
        score_breakdown=scores,
        score_reasons=reasons,
    )
    expected = round(sum(scores[key] * RANKING_WEIGHTS[key] for key in scores), 2)
    assert result.total_score == expected

    with pytest.raises(ValidationError):
        result.model_copy(update={"total_score": 12}).model_validate(
            {**result.model_dump(), "total_score": 12}
        )


def test_execution_record_requires_terminal_timestamp_and_error() -> None:
    now = utc_now()
    with pytest.raises(ValidationError):
        AgentExecutionResult(
            status=AgentStatus.FAILED,
            agent_name="Test Agent",
            input_summary="input",
            decision_summary="failed",
            duration_ms=1,
            started_at=now,
            completed_at=now - timedelta(seconds=1),
        )
