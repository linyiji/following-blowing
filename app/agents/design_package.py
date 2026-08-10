"""Assemble the typed manifest consumed by ExportService."""

from __future__ import annotations

from app.schemas import (
    CandidateDesign,
    DesignPackage,
    IPAdaptationPlan,
    RankingResult,
    REQUIRED_PACKAGE_FILES,
)
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class DesignPackageAgent(BaseAgent[DesignPackage]):
    name = AgentNames.DESIGN_PACKAGE
    prompt_id = "design_package"
    responsibility = "Create the final export manifest and bind every audited workflow artifact."
    handoff = "Design Package manifest → Export Service and results UI"

    def input_summary(self, context: AgentContext) -> str:
        ranking = context.require_output(AgentNames.RANKING, RankingResult)
        return f"Package ranked candidate {ranking.candidate_id} at {ranking.total_score:.2f}/100."

    def process(self, context: AgentContext) -> AgentDecision[DesignPackage]:
        candidate = context.require_output(AgentNames.FUSION_GENERATION, CandidateDesign)
        ranking = context.require_output(AgentNames.RANKING, RankingResult)
        adaptation = context.require_output(AgentNames.IP_ADAPTATION, IPAdaptationPlan)
        if self.ai_provider is None:
            raise RuntimeError("Design Package copy requires an AI provider")
        copy_description = self.ai_provider.generate_text(
            prompt=self.prompt_text,
            context={
                "theme_name": candidate.theme_name,
                "fusion_logic": candidate.fusion_logic,
                "design_tags": candidate.design_tags,
                "fixed_ranking_total": ranking.total_score,
                "target_action": adaptation.target_action,
                "target_pose": adaptation.target_pose,
            },
            model_role="fast",
            demo_output=(
                f"「{candidate.theme_name}」让角色以{adaptation.target_action}进入品牌情境，"
                "通过姿势、行为、产品互动与服装结构形成有机联名，同时遵守IP身份语法。"
            ),
        ).strip()
        manifest = {
            "result.png": candidate.image_uri,
            "creative_brief.json": AgentNames.CREATIVE_BRIEF,
            "ip_identity_grammar.json": AgentNames.IP_INTELLIGENCE,
            "ip_identity.json": AgentNames.IP_INTELLIGENCE,
            "brand_profile.json": AgentNames.BRAND_INTELLIGENCE,
            "brand_feature_pool.json": AgentNames.BRAND_FEATURE,
            "fusion_strategy.json": AgentNames.FUSION_DECISION,
            "ip_adaptation.json": AgentNames.IP_ADAPTATION,
            "guardian_report.json": AgentNames.IP_GUARDIAN,
            "ranking.json": AgentNames.RANKING,
            "workflow_trace.json": "execution_records",
            "design_guide.md": "generated design guidance",
            "prompt_trace.json": "versioned prompt metadata",
        }
        output = DesignPackage(
            package_schema_version=2,
            result_image_uri=candidate.image_uri,
            files=list(REQUIRED_PACKAGE_FILES),
            manifest=manifest,
            copy_description=copy_description,
        )
        return AgentDecision(
            output=output,
            decision_summary=(
                "Luna generated the concept copy; Python created the complete auditable export "
                "manifest tied to audited outputs."
            ),
            output_summary=f"{output.package_name} manifest is ready for ZIP export.",
            evidence=(
                f"Guardian-approved ranking: {ranking.total_score:.2f}",
                *output.files,
            ),
        )
