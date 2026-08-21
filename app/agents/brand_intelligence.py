"""Extract an auditable brand profile from the supplied brand reference."""

from __future__ import annotations

from app.schemas import BrandProfile
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class BrandIntelligenceAgent(BaseAgent[BrandProfile]):
    name = AgentNames.BRAND_INTELLIGENCE
    prompt_id = "brand_intelligence"
    responsibility = "Identify stable brand codes that can be used without overwhelming the IP."
    handoff = "Brand Profile → Brand Collaboration and Brand Feature Agents"

    def input_summary(self, context: AgentContext) -> str:
        return f"Analyze brand reference for {context.input_assets.brand_name}."

    def process(self, context: AgentContext) -> AgentDecision[BrandProfile]:
        brand_name = context.input_assets.brand_name
        if self.ai_provider is None:
            raise RuntimeError("Brand Intelligence requires an AI provider")

        demo_output = BrandProfile(
            brand_name=brand_name,
            brand_summary="Brand profile derived conservatively from the supplied visual reference.",
            logo_features=["primary logo geometry visible in the reference"],
            color_palette=["dominant reference color", "supporting reference color"],
            product_elements=["visible product or packaging cue from the reference"],
            visual_language=["clear silhouette", "high-recognition color blocking", "simple geometry"],
            evidence=["User-provided brand image"],
        )
        output = self.ai_provider.analyze_multimodal(
            images=[context.input_assets.brand_image],
            prompt=f"{self.prompt_text}\n\nRuntime brand label: {brand_name}",
            response_model=BrandProfile,
            model_role="main",
            image_detail="auto",
            demo_output=demo_output.model_dump(mode="json"),
        )
        if not isinstance(output, BrandProfile):
            output = BrandProfile.model_validate(output)
        # The workflow label is user-owned metadata; image analysis must not silently rename it.
        output = output.model_copy(update={"brand_name": brand_name})
        return AgentDecision(
            output=output,
            decision_summary=(
                "Terra Vision extracted logo, color, product, and visual-language cues from the "
                "supplied brand image without applying a hard-coded brand template."
            ),
            output_summary=f"Terra Vision brand profile created for {brand_name}.",
            evidence=tuple(output.evidence),
        )
