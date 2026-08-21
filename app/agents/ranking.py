"""Rank only Guardian-approved candidates using the mandated weights."""

from __future__ import annotations

from app.errors import GuardianRejectedError
from app.providers.demo_ai import DemoAIProvider
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
                f"方案按固定优先级响应了 {intent_count} 项用户约束。"
            ),
            "ip_identity_consistency": (
                f"Guardian 以 {guardian.identity_score:.2f} 分通过候选图；此项直接复用该分数，未作修改。"
            ),
            "brand_recognition": (
                f"方案使用了 {brand.brand_name} 的 {brand_cue_count} 类受控品牌线索。"
            ),
            "fusion_naturalness": (
                f"融合深度为 {depth.value}；评分依据角色行为、产品、服装与场景关系，而非简单贴图。"
            ),
            "commercial_value": (
                f"{depth.value} 融合关系可用于传播画面、产品与衍生品场景。"
            ),
            "historical_collaboration_reference": (
                f"共有 {len(research.results)} 条有来源的历史联名资料提供支持。"
                if research.results
                else "没有可用的有来源历史联名资料，因此该维度采用保守评分。"
            ),
            "innovation": (
                f"创新性依据 {depth.value} 是否超越 Logo、配色和机械堆叠来判断。"
            ),
        }
        if self.ai_provider is None:
            raise RuntimeError("Ranking narrative requires an AI provider")
        demo_narrative = RankingNarrative(
            score_reasons=reasons,
            evidence=[
                f"Guardian 身份一致性分数：{guardian.identity_score:.2f}",
                f"已使用品牌特征类别：{brand_cue_count}",
                f"可用历史参考数量：{len(research.results)}",
            ],
            explanation=(
                "固定的 Python 评分综合衡量用户目标、IP 身份一致性、品牌识别、"
                "融合质量、商业价值、历史参考与创新性。"
            ),
        )
        narrative_warning: str | None = None
        if isinstance(self.ai_provider, DemoAIProvider):
            narrative = self.ai_provider.generate_structured(
                prompt=self.prompt_text,
                response_model=RankingNarrative,
                context={
                    "fixed_score_breakdown": scores,
                    "fixed_score_reasons": reasons,
                    "guardian_identity_score": guardian.identity_score,
                    "guardian_verdict": guardian.verdict.value,
                    "user_constraints": context.user_intent.prioritized_constraints(),
                    "brand_summary": {
                        "name": brand.brand_name,
                        "feature_count": len(brand.features),
                        "cue_categories_used": brand_cue_count,
                    },
                    "fusion_summary": {
                        "depth": depth.value,
                        "interaction": strategy.fusion_relationship.interaction,
                        "behavior": strategy.fusion_relationship.behavior,
                    },
                    "adaptation_summary": {
                        "target_action": adaptation.target_action,
                        "target_pose": adaptation.target_pose,
                    },
                    "historical_reference_count": len(research.results),
                },
                model_role="main",
                demo_output=demo_narrative.model_dump(mode="json"),
            )
        else:
            # Ranking numbers and their auditable base reasons are entirely
            # Python-owned. The compatible gateway currently rejects this
            # optional narrative schema after a long wait, so live runs avoid
            # blocking the workflow on non-authoritative prose.
            narrative = demo_narrative
            narrative_warning = "评分与分项由 Python 固定计算，并已生成中文审计理由。"
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
            warnings=(narrative_warning,) if narrative_warning else (),
        )
