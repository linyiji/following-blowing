"""Rank only Guardian-approved candidates using the mandated weights."""

from __future__ import annotations

from app.errors import GuardianRejectedError
from app.schemas import (
    BrandFeaturePool,
    CandidateDesign,
    CollaborationResearch,
    FusionDepth,
    FusionStrategy,
    GuardianResult,
    GuardianVerdict,
    IPAdaptationPlan,
    RankingNarrative,
    RankingResult,
)
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class RankingAgent(BaseAgent[RankingResult]):
    name = AgentNames.RANKING
    prompt_id = "ranking"
    responsibility = "Score Guardian-approved work across seven auditable commercial dimensions."
    handoff = "Structured score, breakdown, and reasons → Design Package Agent"

    def input_summary(self, context: AgentContext) -> str:
        candidate = context.require_output(AgentNames.FUSION_GENERATION, CandidateDesign)
        guardian = context.require_output(AgentNames.IP_GUARDIAN, GuardianResult)
        return f"Rank Guardian-{guardian.verdict.value} candidate {candidate.candidate_id}."

    def process(self, context: AgentContext) -> AgentDecision[RankingResult]:
        candidate = context.require_output(AgentNames.FUSION_GENERATION, CandidateDesign)
        guardian = context.require_output(AgentNames.IP_GUARDIAN, GuardianResult)
        if guardian.verdict != GuardianVerdict.PASS:
            raise GuardianRejectedError(
                "Only Guardian PASS candidates may enter Ranking",
                context={
                    "candidate_id": candidate.candidate_id,
                    "guardian_verdict": guardian.verdict.value,
                },
            )
        if guardian.candidate_id != candidate.candidate_id:
            raise GuardianRejectedError(
                "Guardian result does not belong to the candidate being ranked",
                context={
                    "candidate_id": candidate.candidate_id,
                    "guardian_candidate_id": guardian.candidate_id,
                },
            )
        strategy = context.require_output(AgentNames.FUSION_DECISION, FusionStrategy)
        adaptation = context.require_output(AgentNames.IP_ADAPTATION, IPAdaptationPlan)
        brand = context.require_output(AgentNames.BRAND_FEATURE, BrandFeaturePool)
        research = context.require_output(
            AgentNames.BRAND_COLLABORATION, CollaborationResearch
        )

        intent_count = len(context.user_intent.prioritized_constraints())
        brand_cue_count = sum(
            bool(value)
            for value in (
                strategy.clothing,
                strategy.headwear,
                strategy.brand_accessories,
                strategy.held_items,
                strategy.scene,
                strategy.palette,
            )
        )
        organic_scores = {
            FusionDepth.STICKER: (55.0, 68.0, 50.0),
            FusionDepth.COLOR: (64.0, 72.0, 58.0),
            FusionDepth.ACCESSORY: (72.0, 78.0, 67.0),
            FusionDepth.APPAREL: (82.0, 86.0, 76.0),
            FusionDepth.PRODUCT_INTERACTION: (90.0, 91.0, 88.0),
            FusionDepth.BEHAVIOR: (92.0, 92.0, 91.0),
            FusionDepth.ROLE: (93.0, 94.0, 92.0),
            FusionDepth.NARRATIVE: (95.0, 95.0, 95.0),
        }
        depth = strategy.fusion_relationship.fusion_depth
        fusion_score, commercial_score, innovation_score = organic_scores[depth]
        if adaptation.interaction_plan.product_interaction:
            fusion_score = min(96.0, fusion_score + 1.0)
        scores = {
            "user_goal_match": min(96.0, 86.0 + min(intent_count, 5) * 2.0),
            "ip_identity_consistency": guardian.identity_score,
            "brand_recognition": min(95.0, 80.0 + brand_cue_count * 2.5),
            "fusion_naturalness": fusion_score,
            "commercial_value": commercial_score,
            "historical_collaboration_reference": 82.0 if research.results else 50.0,
            "innovation": innovation_score,
        }
        reasons = {
            "user_goal_match": (
                f"The strategy addresses {intent_count} prioritized user constraint(s) in fixed priority order."
            ),
            "ip_identity_consistency": (
                f"Guardian passed the candidate at {guardian.identity_score:.2f}; this value is reused without modification."
            ),
            "brand_recognition": (
                f"The concept uses {brand_cue_count} controlled cue categories from {brand.brand_name}."
            ),
            "fusion_naturalness": (
                f"Fusion depth is {depth.value}; the score rewards behavior, role, product, apparel, "
                "and scene relationships and penalizes sticker-like application."
            ),
            "commercial_value": (
                f"The {depth.value} relationship is evaluated for campaign, product, and merchandise use."
            ),
            "historical_collaboration_reference": (
                f"Supported by {len(research.results)} sourced historical reference(s)."
                if research.results
                else "No sourced historical reference was available, so this dimension is conservatively scored."
            ),
            "innovation": (
                f"Innovation reflects whether {depth.value} goes beyond logo, color, and mechanical stacking."
            ),
        }
        if self.ai_provider is None:
            raise RuntimeError("Ranking narrative requires an AI provider")
        demo_narrative = RankingNarrative(
            score_reasons=reasons,
            evidence=[
                f"Guardian identity_score: {guardian.identity_score:.2f}",
                f"Brand feature categories used: {brand_cue_count}",
                f"Historical references available: {len(research.results)}",
            ],
            explanation=(
                "The fixed Python breakdown balances user fit and IP identity with brand "
                "recognition, fusion quality, commercial value, precedent, and innovation."
            ),
        )
        narrative = self.ai_provider.generate_structured(
            prompt=self.prompt_text,
            response_model=RankingNarrative,
            context={
                "fixed_score_breakdown": scores,
                "guardian_identity_score": guardian.identity_score,
                "user_constraints": context.user_intent.prioritized_constraints(),
                "brand_feature_pool": brand.model_dump(mode="json"),
                "fusion_strategy": strategy.model_dump(mode="json"),
                "fusion_relationship": strategy.fusion_relationship.model_dump(mode="json"),
                "ip_adaptation_plan": adaptation.model_dump(mode="json"),
                "historical_reference_count": len(research.results),
            },
            model_role="main",
            demo_output=demo_narrative.model_dump(mode="json"),
        )
        if not isinstance(narrative, RankingNarrative):
            narrative = RankingNarrative.model_validate(narrative)
        narrative_reasons = {
            key: narrative.score_reasons.get(key, reasons[key]) or reasons[key]
            for key in scores
        }

        output = RankingResult.from_scores(
            candidate_id=candidate.candidate_id,
            score_breakdown=scores,
            score_reasons=narrative_reasons,
            evidence=narrative.evidence,
            explanation=narrative.explanation,
        )
        return AgentDecision(
            output=output,
            decision_summary=(
                f"Calculated a weighted total of {output.total_score:.2f}; all seven dimensions include reasons."
            ),
            output_summary=f"Candidate ranked {output.total_score:.2f}/100.",
            evidence=tuple([*narrative_reasons.values(), *narrative.evidence]),
        )
