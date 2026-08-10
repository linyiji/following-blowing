"""Terra pose-aware dual-image review with Python-owned scoring and gates."""

from __future__ import annotations

import json
from typing import Any

from app.schemas import (
    GUARDIAN_COMPLIANCE_GATES,
    GUARDIAN_REQUIRED_CHECKS,
    CandidateDesign,
    CreativeBrief,
    FusionStrategy,
    GuardianCheck,
    GuardianCheckSet,
    GuardianResult,
    GuardianVerdict,
    GuardianVisionAssessment,
    IPAdaptationPlan,
    IPIntelligenceResult,
    calculate_guardian_identity_score,
    guardian_verdict_for_assessment,
)
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


def _demo_assessment(
    score: float,
    *,
    target_pose: float | None = None,
    user_intent: float | None = None,
    brand_integration: float | None = None,
) -> GuardianVisionAssessment:
    values = {key: score for key in GUARDIAN_REQUIRED_CHECKS}
    values["target_pose_compliance"] = score if target_pose is None else target_pose
    values["user_intent_compliance"] = score if user_intent is None else user_intent
    values["brand_integration_compliance"] = (
        score if brand_integration is None else brand_integration
    )
    identity_score = calculate_guardian_identity_score(values)
    verdict = guardian_verdict_for_assessment(identity_score, values)
    instruction = None
    if verdict != GuardianVerdict.PASS:
        instruction = (
            "Correct identity anchors and facial relationships; complete the target pose and "
            "turn brand graphics into apparel, product, behavior, or scene integration."
        )
    return GuardianVisionAssessment(
        verdict=verdict,
        checks=GuardianCheckSet(
            **{
                key: GuardianCheck(
                    score=value,
                    reason=f"Deterministic pose-aware demo assessment for {key}.",
                )
                for key, value in values.items()
            }
        ),
        major_differences=[] if verdict == GuardianVerdict.PASS else ["Correction required"],
        preserve=["identity anchors", "facial grammar", "proportion signature", "line grammar"],
        change_only=["pose", "viewpoint", "limbs", "expression", "clothing", "held objects"],
        candidate_pose="Target action pose",
        allowed_transformations=[
            "pose change",
            "viewpoint change",
            "limb movement",
            "body orientation",
            "expression within grammar",
            "clothing, accessories, and held objects",
        ],
        identity_drift=[] if verdict == GuardianVerdict.PASS else ["Review low identity checks"],
        identity_corrections=[] if verdict == GuardianVerdict.PASS else ["Restore identity anchors"],
        pose_corrections=[] if values["target_pose_compliance"] >= 75 else ["Complete target pose"],
        brand_corrections=(
            []
            if values["brand_integration_compliance"] >= 75
            else ["Integrate brand cue through behavior, product, apparel, or scene"]
        ),
        style_corrections=[] if verdict == GuardianVerdict.PASS else ["Restore line-style grammar"],
        revision_instruction=instruction,
    )


def _sequence_value(metadata: dict[str, Any], key: str, index: int, fallback: float) -> float:
    values = metadata.get(key)
    if isinstance(values, list) and index < len(values):
        return float(values[index])
    return fallback


class IPGuardianAgent(BaseAgent[GuardianResult]):
    name = AgentNames.IP_GUARDIAN
    prompt_id = "ip_guardian"
    responsibility = (
        "Decide whether the transformed candidate follows the same IP Identity Grammar and "
        "complies with pose, intent, and brand-integration gates."
    )
    handoff = "Python PASS → Ranking; Python REJECT/REVISE → Fusion Generation"

    def input_summary(self, context: AgentContext) -> str:
        candidate = context.require_output(AgentNames.FUSION_GENERATION, CandidateDesign)
        adaptation = context.require_output(AgentNames.IP_ADAPTATION, IPAdaptationPlan)
        return (
            f"Compare original IP with candidate {candidate.candidate_id} for target pose "
            f"'{adaptation.target_pose}', revision {candidate.revision_number}."
        )

    def process(self, context: AgentContext) -> AgentDecision[GuardianResult]:
        candidate = context.require_output(AgentNames.FUSION_GENERATION, CandidateDesign)
        ip_result = context.require_output(AgentNames.IP_INTELLIGENCE, IPIntelligenceResult)
        grammar = ip_result.identity_grammar
        if grammar is None:
            raise ValueError("Pose-Aware Guardian requires IP Identity Grammar")
        adaptation = context.require_output(AgentNames.IP_ADAPTATION, IPAdaptationPlan)
        brief = context.require_output(AgentNames.CREATIVE_BRIEF, CreativeBrief)
        strategy = context.require_output(AgentNames.FUSION_DECISION, FusionStrategy)
        if self.ai_provider is None:
            raise RuntimeError("IP Guardian requires an AI provider")

        metadata = dict(context.user_intent.metadata)
        forced_scores = metadata.get("guardian_score_sequence")
        demo_score = 90.0
        if isinstance(forced_scores, list) and context.guardian_retries < len(forced_scores):
            demo_score = float(forced_scores[context.guardian_retries])
        demo_output = _demo_assessment(
            demo_score,
            target_pose=_sequence_value(
                metadata,
                "guardian_target_pose_sequence",
                context.guardian_retries,
                demo_score,
            ),
            user_intent=_sequence_value(
                metadata,
                "guardian_user_intent_sequence",
                context.guardian_retries,
                demo_score,
            ),
            brand_integration=_sequence_value(
                metadata,
                "guardian_brand_integration_sequence",
                context.guardian_retries,
                demo_score,
            ),
        )

        prompt = (
            f"{self.prompt_text}\n\n"
            "IP_IDENTITY_GRAMMAR:\n"
            f"{json.dumps(grammar.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "IP_ADAPTATION_PLAN:\n"
            f"{json.dumps(adaptation.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "CREATIVE_BRIEF:\n"
            f"{json.dumps(brief.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "FUSION_RELATIONSHIP:\n"
            f"{json.dumps(strategy.fusion_relationship.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "PRIORITIZED_USER_INTENT:\n"
            f"{json.dumps(context.user_intent.prioritized_constraints(), ensure_ascii=False)}"
        )
        assessment = self.ai_provider.analyze_multimodal(
            images=[context.input_assets.ip_image, candidate.image_uri],
            prompt=prompt,
            response_model=GuardianVisionAssessment,
            model_role="main",
            demo_output=demo_output.model_dump(mode="json"),
        )
        if not isinstance(assessment, GuardianVisionAssessment):
            assessment = GuardianVisionAssessment.model_validate(assessment)

        raw_checks = assessment.checks.model_dump(mode="python")
        checks = {key: float(value["score"]) for key, value in raw_checks.items()}
        check_reasons = {key: str(value["reason"]) for key, value in raw_checks.items()}
        identity_score = calculate_guardian_identity_score(checks)
        verdict = guardian_verdict_for_assessment(
            identity_score,
            checks,
            severe_forbidden_drift=assessment.severe_forbidden_drift,
        )

        identity_corrections = list(assessment.identity_corrections)
        pose_corrections = list(assessment.pose_corrections)
        brand_corrections = list(assessment.brand_corrections)
        style_corrections = list(assessment.style_corrections)
        intent_corrections: list[str] = []
        if identity_score < 85 and not identity_corrections:
            low_identity = [
                key for key in GUARDIAN_REQUIRED_CHECKS
                if key not in GUARDIAN_COMPLIANCE_GATES and checks[key] < 85
            ]
            identity_corrections = [f"Correct {key}" for key in low_identity]
        if checks["target_pose_compliance"] < 75 and not pose_corrections:
            pose_corrections = [f"Complete target pose: {adaptation.target_pose}"]
        if checks["brand_integration_compliance"] < 75 and not brand_corrections:
            brand_corrections = [
                "Replace sticker-like cues with product, behavior, role, apparel, or scene integration"
            ]
        if checks["user_intent_compliance"] < 75:
            constraints = context.user_intent.prioritized_constraints()
            intent_corrections = [
                "Satisfy the prioritized user constraints: "
                + ("; ".join(constraints) if constraints else "the approved Creative Brief")
            ]

        revision_instruction: str | None = None
        if verdict != GuardianVerdict.PASS:
            grouped = [
                *(f"Identity: {item}" for item in identity_corrections),
                *(f"Pose: {item}" for item in pose_corrections),
                *(f"Intent: {item}" for item in intent_corrections),
                *(f"Brand: {item}" for item in brand_corrections),
                *(f"Style: {item}" for item in style_corrections),
            ]
            revision_instruction = (assessment.revision_instruction or "").strip() or "; ".join(grouped)
            if not revision_instruction:
                revision_instruction = (
                    "Restore the IP Identity Grammar and complete the approved pose and organic "
                    "brand relationship."
                )

        findings = [
            f"{key}: {checks[key]:.1f}/100 — {check_reasons[key]}"
            for key in GUARDIAN_REQUIRED_CHECKS
        ]
        if assessment.verdict is not None and assessment.verdict != verdict:
            findings.append(
                f"Terra qualitative verdict was {assessment.verdict.value}; Python score/gates "
                f"produced authoritative {verdict.value}."
            )
        if assessment.severe_forbidden_drift:
            findings.append("Python applied the severe forbidden-drift REJECT gate.")
        findings.extend(f"Intent correction: {item}" for item in intent_corrections)

        output = GuardianResult(
            candidate_id=candidate.candidate_id,
            identity_score=identity_score,
            score=identity_score,
            verdict=verdict,
            checks=checks,
            check_reasons=check_reasons,
            major_differences=assessment.major_differences,
            preserve=assessment.preserve or grammar.core_identity_anchors,
            change_only=assessment.change_only or grammar.mutable_features,
            findings=findings,
            intent_constraints_met=checks["user_intent_compliance"] >= 75,
            target_pose_compliance=checks["target_pose_compliance"],
            user_intent_compliance=checks["user_intent_compliance"],
            brand_integration_compliance=checks["brand_integration_compliance"],
            original_pose=ip_result.ip_dna.pose,
            target_pose=adaptation.target_pose,
            candidate_pose=assessment.candidate_pose,
            allowed_transformations=assessment.allowed_transformations,
            identity_drift=assessment.identity_drift,
            forbidden_drift_detected=assessment.forbidden_drift_detected,
            severe_forbidden_drift=assessment.severe_forbidden_drift,
            identity_corrections=identity_corrections,
            pose_corrections=pose_corrections,
            brand_corrections=brand_corrections,
            style_corrections=style_corrections,
            revision_instruction=revision_instruction,
            retry_count=context.guardian_retries,
            scoring_version="pose_aware_grammar_v3",
        )
        return AgentDecision(
            output=output,
            decision_summary=(
                f"Pose-Aware Guardian {verdict.value}: Python identity score {identity_score:.2f}; "
                f"pose/intent/brand gates {checks['target_pose_compliance']:.0f}/"
                f"{checks['user_intent_compliance']:.0f}/"
                f"{checks['brand_integration_compliance']:.0f}."
            ),
            output_summary=f"Pose-Aware Guardian verdict {verdict.value} at {identity_score:.2f}/100.",
            evidence=tuple(findings),
            warnings=(revision_instruction,) if revision_instruction else (),
        )
