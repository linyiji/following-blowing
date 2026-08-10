"""Plan how the character changes pose while preserving identity grammar."""

from __future__ import annotations

from app.schemas import (
    BrandAttachmentPlan,
    BrandFeaturePool,
    CreativeBrief,
    DeformationMap,
    FusionStrategy,
    IPAdaptationPlan,
    IPIntelligenceResult,
    IdentityPreservationPlan,
    InteractionPlan,
    PoseBlueprint,
    TransformationLevel,
)
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class IPAdaptationAgent(BaseAgent[IPAdaptationPlan]):
    name = AgentNames.IP_ADAPTATION
    prompt_id = "ip_adaptation"
    responsibility = (
        "Specify how the IP changes action, pose, view, deformation, and attachments while "
        "remaining governed by the same identity grammar."
    )
    handoff = "Pose-aware IP Adaptation Plan → Fusion Generation Agent"

    def input_summary(self, context: AgentContext) -> str:
        brief = context.require_output(AgentNames.CREATIVE_BRIEF, CreativeBrief)
        return (
            f"Adapt the IP for '{brief.desired_action}' at "
            f"{brief.transformation_level.value} transformation level."
        )

    def process(self, context: AgentContext) -> AgentDecision[IPAdaptationPlan]:
        intelligence = context.require_output(
            AgentNames.IP_INTELLIGENCE, IPIntelligenceResult
        )
        grammar = intelligence.identity_grammar
        if grammar is None:
            raise ValueError("IP Adaptation requires IP Identity Grammar")
        brief = context.require_output(AgentNames.CREATIVE_BRIEF, CreativeBrief)
        strategy = context.require_output(AgentNames.FUSION_DECISION, FusionStrategy)
        brand = context.require_output(AgentNames.BRAND_FEATURE, BrandFeaturePool)
        if self.ai_provider is None:
            raise RuntimeError("IP Adaptation requires an AI provider")

        is_high = brief.transformation_level == TransformationLevel.HIGH
        target_pose = (
            "Reconstructed action pose that clearly performs the requested action"
            if is_high
            else "Natural pose adjusted to support the selected interaction"
        )
        generation_instructions = [
            "Use the original image as an identity reference, not a frozen pose template.",
            "Reconstruct limb overlap and body orientation for the target action.",
            "Preserve identity anchors and relational rules after deformation.",
        ]
        if is_high:
            generation_instructions.extend(
                [
                    "Re-pose the character explicitly.",
                    "Do not simply overlay brand assets on the original pose.",
                ]
            )
        demo_output = IPAdaptationPlan(
            target_action=brief.desired_action,
            target_pose=target_pose,
            view_angle=brief.desired_view,
            transformation_level=brief.transformation_level,
            pose_blueprint=PoseBlueprint(
                head_orientation="Orient toward the primary interaction while preserving face grammar",
                body_axis="Shift naturally to support balance and action",
                left_limb="Articulate as a support or gesture limb",
                right_limb="Articulate toward the primary held object or gesture",
                legs="Reconstruct for a stable target pose",
                tail_if_applicable="Project consistently with view; omit only if not applicable",
                ear_behavior="Follow head rotation while retaining ear grammar and attachment",
                facial_projection="Project the eye/nose-mouth relationships for the selected view",
            ),
            deformation_map=DeformationMap(
                preserve=grammar.core_identity_anchors,
                transform=["pose", "viewpoint", "limb position", "body orientation"],
                pose_dependent=grammar.pose_dependent_features,
                forbidden=grammar.forbidden_drift,
            ),
            identity_preservation=IdentityPreservationPlan(
                anchors_to_preserve=grammar.core_identity_anchors,
                relational_rules=grammar.relational_geometry,
                proportion_rules=grammar.proportion_signature,
                facial_rules=grammar.facial_grammar,
                line_style_rules=grammar.line_style_grammar,
            ),
            brand_attachment=BrandAttachmentPlan(
                clothing=strategy.clothing,
                headwear=strategy.headwear,
                held_objects=strategy.held_items,
                logo_application=strategy.brand_accessories,
                color_application=strategy.palette,
            ),
            interaction_plan=InteractionPlan(
                product_interaction=strategy.fusion_relationship.product_interaction,
                environment_interaction=strategy.fusion_relationship.scene_integration,
                behavior=strategy.fusion_relationship.behavior,
            ),
            occlusion_rules=grammar.occlusion_rules,
            attachment_rules=[
                *grammar.accessory_attachment_rules,
                *grammar.clothing_adaptation_rules,
            ],
            generation_instructions=generation_instructions,
            negative_constraints=grammar.forbidden_drift,
        )
        output = self.ai_provider.generate_structured(
            prompt=self.prompt_text,
            response_model=IPAdaptationPlan,
            context={
                "ip_identity_grammar": grammar.model_dump(mode="json"),
                "creative_brief": brief.model_dump(mode="json"),
                "fusion_strategy": strategy.model_dump(mode="json"),
                "fusion_relationship": strategy.fusion_relationship.model_dump(mode="json"),
                "brand_feature_pool": brand.model_dump(mode="json"),
                "user_intent": context.user_intent.model_dump(mode="json"),
            },
            model_role="main",
            demo_output=demo_output.model_dump(mode="json"),
        )
        if not isinstance(output, IPAdaptationPlan):
            output = IPAdaptationPlan.model_validate(output)

        user_requests_frozen_pose = any(
            phrase in context.user_intent.goal_text.casefold()
            for phrase in ("保持原始姿势", "保持原姿势", "keep the original pose")
        )
        instructions = list(output.generation_instructions)
        if not user_requests_frozen_pose:
            frozen_phrases = (
                "保持原始姿势",
                "保持原姿势",
                "keep original pose",
                "keep the original pose",
                "exact original pose",
            )
            instructions = [
                instruction
                for instruction in instructions
                if not any(phrase in instruction.casefold() for phrase in frozen_phrases)
            ]
        if output.transformation_level == TransformationLevel.HIGH:
            for instruction in (
                "Re-pose the character explicitly.",
                "Do not simply overlay brand assets on the original pose.",
            ):
                if instruction.casefold() not in {item.casefold() for item in instructions}:
                    instructions.append(instruction)
        output = output.model_copy(
            update={
                "deformation_map": output.deformation_map.model_copy(
                    update={
                        "preserve": list(
                            dict.fromkeys(
                                [
                                    *grammar.core_identity_anchors,
                                    *output.deformation_map.preserve,
                                ]
                            )
                        ),
                        "forbidden": list(
                            dict.fromkeys(
                                [*grammar.forbidden_drift, *output.deformation_map.forbidden]
                            )
                        ),
                    }
                ),
                "generation_instructions": instructions,
                "negative_constraints": list(
                    dict.fromkeys([*grammar.forbidden_drift, *output.negative_constraints])
                ),
            }
        )
        return AgentDecision(
            output=output,
            decision_summary=(
                f"Terra produced a {output.transformation_level.value} pose-aware adaptation "
                "with explicit deformation, identity, attachment, interaction, and occlusion rules."
            ),
            output_summary=f"IP Adaptation targets: {output.target_pose}.",
            evidence=tuple(output.identity_preservation.anchors_to_preserve),
        )
