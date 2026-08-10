"""Distill brand evidence into features with integration affordances."""

from __future__ import annotations

from app.schemas import BrandFeature, BrandFeaturePool, BrandProfile, CollaborationResearch
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class BrandFeatureAgent(BaseAgent[BrandFeaturePool]):
    name = AgentNames.BRAND_FEATURE
    prompt_id = "brand_feature"
    responsibility = (
        "Create an evidenced Brand Feature Pool and state how each cue can integrate organically."
    )
    handoff = "Brand Feature Pool + Integration Affordances → Creative Brief and IP Adaptation"

    def input_summary(self, context: AgentContext) -> str:
        profile = context.require_output(AgentNames.BRAND_INTELLIGENCE, BrandProfile)
        research = context.require_output(
            AgentNames.BRAND_COLLABORATION, CollaborationResearch
        )
        return f"Distill {profile.brand_name} features with {len(research.results)} sourced precedents."

    def process(self, context: AgentContext) -> AgentDecision[BrandFeaturePool]:
        profile = context.require_output(AgentNames.BRAND_INTELLIGENCE, BrandProfile)
        research = context.require_output(
            AgentNames.BRAND_COLLABORATION, CollaborationResearch
        )
        if self.ai_provider is None:
            raise RuntimeError("Brand Feature requires an AI provider")

        evidence = profile.evidence + [
            f"{result.title}: {result.url}" for result in research.results
        ]
        logo_name = profile.logo_features[0] if profile.logo_features else "primary logo geometry"
        product_name = (
            profile.product_elements[0]
            if profile.product_elements
            else "visible product or packaging cue"
        )
        features = [
            BrandFeature(
                feature_id="logo-01",
                name=logo_name,
                category="logo",
                description="High-recognition graphic cue grounded in the brand reference.",
                recognition_strength=90,
                evidence=profile.evidence,
                integration_affordances=["apparel", "accessory", "graphic_application"],
                preferred_uses=["small uniform chest mark", "badge", "packaging graphic"],
                secondary_uses=["environment signage"],
                avoid_uses=["replace the IP face", "replace ear structure", "floating oversized logo"],
                interaction_modes=["worn graphic", "scene signage"],
                attachment_targets=["clothing panel", "removable accessory", "environment"],
                scale_guidance="Secondary to the face and identity anchors.",
                occlusion_risk="Low when kept off the face and ears.",
                identity_conflict_risk="High if used as replacement anatomy.",
            ),
            BrandFeature(
                feature_id="color-01",
                name="brand color system",
                category="color",
                description="Dominant and supporting colors visible in the reference.",
                recognition_strength=75,
                evidence=profile.evidence,
                integration_affordances=["color_application", "apparel", "environment"],
                preferred_uses=["clothing panels", "small accessories", "scene accents"],
                secondary_uses=["packaging", "graphic borders"],
                avoid_uses=["cover all original line work", "erase facial contrast"],
                interaction_modes=["controlled color blocking"],
                attachment_targets=["apparel", "props", "background accents"],
                scale_guidance="Use as controlled accents rather than full character replacement.",
                occlusion_risk="Low.",
                identity_conflict_risk="Medium when color reduces line-style recognition.",
            ),
            BrandFeature(
                feature_id="product-01",
                name=product_name,
                category="product",
                description="Product cue that can drive character behavior instead of acting as a sticker.",
                recognition_strength=85,
                evidence=profile.evidence,
                integration_affordances=[
                    "held_object",
                    "product_interaction",
                    "role",
                    "environment",
                    "narrative",
                ],
                preferred_uses=["held object", "product interaction", "table object", "pocket interaction"],
                secondary_uses=["scene prop", "narrative trigger"],
                avoid_uses=["replace IP face", "replace ear structure", "obscure all facial anchors"],
                interaction_modes=["hold", "offer", "serve", "look toward", "share"],
                attachment_targets=["hand or paw", "table", "bag or pocket", "environment"],
                scale_guidance="Large enough to read, small enough to preserve character recognition.",
                occlusion_risk="Medium; protect the face and at least one action limb.",
                identity_conflict_risk="Low when treated as an object rather than anatomy.",
            ),
        ]
        demo_output = BrandFeaturePool(
            brand_name=profile.brand_name,
            logo_features=profile.logo_features,
            color_palette=profile.color_palette,
            product_elements=profile.product_elements,
            scene_elements=["retail touchpoint", "campaign key visual"],
            collaboration_patterns=research.patterns,
            evidence=evidence,
            features=features,
            organic_fusion_guidance=[
                "Prefer product interaction, behavior, role, or environment over floating marks.",
                "Never replace face, ear, or body topology with a brand feature.",
            ],
        )
        output = self.ai_provider.generate_structured(
            prompt=self.prompt_text,
            response_model=BrandFeaturePool,
            context={
                "brand_profile": profile.model_dump(mode="json"),
                "collaboration_research": research.model_dump(mode="json"),
            },
            model_role="main",
            demo_output=demo_output.model_dump(mode="json"),
        )
        if not isinstance(output, BrandFeaturePool):
            output = BrandFeaturePool.model_validate(output)
        output = output.model_copy(
            update={
                "brand_name": profile.brand_name,
                "evidence": list(dict.fromkeys([*output.evidence, *evidence])),
            }
        )
        return AgentDecision(
            output=output,
            decision_summary=(
                "Terra mapped evidenced brand cues to apparel, object, behavior, role, scene, "
                "graphic, and color affordances with identity-conflict risks."
            ),
            output_summary=f"{len(output.features)} brand features and integration affordances are ready.",
            evidence=tuple(output.evidence),
            warnings=tuple(research.warnings),
        )
