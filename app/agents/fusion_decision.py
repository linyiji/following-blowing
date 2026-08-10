"""Decide how the IP and brand should relate before pose adaptation."""

from __future__ import annotations

from app.schemas import (
    BrandFeaturePool,
    CreativeBrief,
    FusionDepth,
    FusionRelationship,
    FusionStrategy,
    IPIntelligenceResult,
)
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class FusionDecisionAgent(BaseAgent[FusionStrategy]):
    name = AgentNames.FUSION_DECISION
    prompt_id = "fusion_decision"
    responsibility = "Choose an organic co-branding relationship grounded in intent and affordances."
    handoff = "Fusion Strategy + Fusion Relationship → IP Adaptation Agent"

    def input_summary(self, context: AgentContext) -> str:
        brief = context.require_output(AgentNames.CREATIVE_BRIEF, CreativeBrief)
        return f"Convert creative brief '{brief.theme_name}' into an organic fusion relationship."

    def process(self, context: AgentContext) -> AgentDecision[FusionStrategy]:
        brief = context.require_output(AgentNames.CREATIVE_BRIEF, CreativeBrief)
        brand = context.require_output(AgentNames.BRAND_FEATURE, BrandFeaturePool)
        grammar = context.require_output(
            AgentNames.IP_INTELLIGENCE, IPIntelligenceResult
        ).identity_grammar
        if grammar is None:
            raise ValueError("Fusion Decision requires IP Identity Grammar")
        goals = set(context.user_intent.selected_goals)

        clothing = ["brand-role apparel adapted to the target pose"] if "服装融合" in goals else []
        headwear = ["pose-aware removable brand headwear"] if "帽子 / 头饰" in goals else []
        logo_cue = brand.logo_features[0] if brand.logo_features else "brand mark"
        product_cue = brand.product_elements[0] if brand.product_elements else "brand product cue"
        accessories = [f"small integrated {logo_cue} application"] if "品牌Logo" in goals else []
        held_items = [product_cue] if "产品元素" in goals else []
        scene = ["brand environment supporting the character action"] if "场景融合" in goals else []
        if not any((clothing, headwear, accessories, held_items, scene)):
            held_items = [product_cue]
            scene = ["simple context for product interaction"]

        if "联名故事" in goals:
            depth = FusionDepth.NARRATIVE
        elif "产品元素" in goals or held_items:
            depth = FusionDepth.PRODUCT_INTERACTION
        elif "服装融合" in goals:
            depth = FusionDepth.APPAREL
        elif "帽子 / 头饰" in goals:
            depth = FusionDepth.ACCESSORY
        elif "品牌配色" in goals:
            depth = FusionDepth.COLOR
        else:
            depth = FusionDepth.ROLE

        relationship = FusionRelationship(
            ip_role=brief.desired_character_role,
            brand_role="provides a product, role, apparel system, and environment for action",
            interaction=brief.desired_interaction,
            behavior=brief.desired_action,
            product_interaction=(
                f"The character actively holds, offers, serves, or uses {product_cue}."
                if held_items
                else "No forced product interaction."
            ),
            apparel_integration="; ".join(clothing + headwear),
            graphic_integration=(
                f"Use {logo_cue} as a small structural apparel or prop graphic, never a face replacement."
            ),
            color_integration=f"Apply controlled palette cues: {', '.join(brand.color_palette)}",
            scene_integration="; ".join(scene),
            narrative=(
                "The IP takes an active role in the brand world and performs a legible behavior."
            ),
            fusion_depth=depth,
        )
        design_tags = [
            "IP Identity Grammar",
            "organic brand interaction",
            "commercial key visual",
            depth.value,
            *context.user_intent.selected_goals,
        ]
        negative_prompt = "; ".join(
            f"forbid identity drift: {feature}" for feature in grammar.forbidden_drift
        )
        generation_prompt = (
            f"Create '{brief.theme_name}'. The character role is {relationship.ip_role}. "
            f"Action: {brief.desired_action}. Interaction: {relationship.interaction}. "
            f"Fusion depth: {depth.value}. The original reference defines identity, not a frozen pose."
        )
        demo_output = FusionStrategy(
            theme_name=brief.theme_name,
            fusion_logic=(
                "Brand recognition enters through character behavior, product interaction, role, "
                "pose-aware apparel, graphics, controlled color, and scene—not mechanical overlays."
            ),
            clothing=clothing,
            headwear=headwear,
            brand_accessories=accessories,
            held_items=held_items,
            scene=scene,
            palette=brand.color_palette,
            design_tags=list(dict.fromkeys(design_tags)),
            generation_prompt=generation_prompt,
            negative_prompt=negative_prompt,
            fusion_relationship=relationship,
        )
        if self.ai_provider is None:
            raise RuntimeError("Fusion Decision requires an AI provider")
        output = self.ai_provider.generate_structured(
            prompt=self.prompt_text,
            response_model=FusionStrategy,
            context={
                "creative_brief": brief.model_dump(mode="json"),
                "brand_feature_pool": brand.model_dump(mode="json"),
                "ip_identity_grammar": grammar.model_dump(mode="json"),
                "prioritized_user_constraints": context.user_intent.prioritized_constraints(),
            },
            model_role="main",
            demo_output=demo_output.model_dump(mode="json"),
        )
        if not isinstance(output, FusionStrategy):
            output = FusionStrategy.model_validate(output)

        required_negative = [
            f"forbid identity drift: {feature}"
            for feature in grammar.forbidden_drift
            if feature.casefold() not in output.negative_prompt.casefold()
        ]
        guarded_negative = "; ".join(
            item for item in (output.negative_prompt, *required_negative) if item
        )
        prompt_prefix = (
            "Use the original IP as an identity reference, not a frozen pose template. "
            f"Preserve identity anchors: {', '.join(grammar.core_identity_anchors)}. "
            f"Honor user constraints: {context.user_intent.prioritized_constraints()}. "
        )
        output = output.model_copy(
            update={
                "palette": output.palette or brand.color_palette,
                "design_tags": list(
                    dict.fromkeys([*output.design_tags, *context.user_intent.selected_goals])
                ),
                "generation_prompt": prompt_prefix + output.generation_prompt,
                "negative_prompt": guarded_negative,
            }
        )
        return AgentDecision(
            output=output,
            decision_summary=(
                f"Selected {output.fusion_relationship.fusion_depth.value} fusion and defined the "
                "IP/brand role, behavior, product, apparel, graphic, color, and scene relationship."
            ),
            output_summary="Terra Fusion Strategy and Fusion Relationship created.",
            evidence=tuple([*grammar.core_identity_anchors, *brief.evidence[:3]]),
        )
