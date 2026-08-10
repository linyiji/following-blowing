"""Opt-in, one-call Terra smoke test for the IP Adaptation Agent.

The smoke builds strict deterministic upstream fixtures around the packaged
demo IP, then asks Terra for exactly one ``IPAdaptationPlan``.  It never creates
an image and never prints credentials, provider URLs, or local absolute paths.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.base import AgentContext  # noqa: E402
from app.agents.ip_adaptation import IPAdaptationAgent  # noqa: E402
from app.config import MAIN_MODEL, load_settings  # noqa: E402
from app.providers import DemoAIProvider, create_ai_provider  # noqa: E402
from app.schemas import (  # noqa: E402
    BrandAttachmentPlan,
    BrandFeature,
    BrandFeaturePool,
    CreativeBrief,
    DeformationMap,
    FusionDepth,
    FusionRelationship,
    FusionStrategy,
    IPAdaptationPlan,
    IPDNA,
    IPIdentityGrammar,
    IPIntelligenceResult,
    IdentityPreservationPlan,
    InputAssets,
    InteractionPlan,
    PoseBlueprint,
    TransformationLevel,
    UserIntent,
)
from app.workflow.graph import AgentNames  # noqa: E402


IP_REFERENCE = PROJECT_ROOT / "assets" / "demo" / "ip_reference.jpg"
BRAND_REFERENCE = PROJECT_ROOT / "assets" / "demo" / "brand_reference.jpg"


def load_real_terra() -> tuple[Any, Any] | None:
    """Return current settings/provider, or emit a safe opt-in SKIP."""

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    secrets: dict[str, Any] = {}
    if secrets_path.is_file():
        try:
            secrets = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            print("SKIP: local provider configuration is unavailable")
            return None
    settings = load_settings(project_root=PROJECT_ROOT, secrets=secrets)
    if not settings.multimodal.api_key:
        print("SKIP: MULTIMODAL_API_KEY/OPENAI_API_KEY is not configured")
        return None
    if settings.model_main != MAIN_MODEL:
        print("SKIP: MAIN model route is not the required Terra model")
        return None
    provider = create_ai_provider(settings)
    if settings.demo_mode or isinstance(provider, DemoAIProvider):
        print("SKIP: configured AI provider resolves to demo mode")
        return None
    return settings, provider


def identity_fixture() -> IPIntelligenceResult:
    """Strict identity grammar grounded in the packaged minimal line-art IP."""

    ip_dna = IPDNA(
        character_type="Minimal rounded line-art mascot",
        full_body_structure="Large rounded head, compact torso, and short simplified limbs",
        silhouette="Rounded projected envelope that may change naturally with pose",
        head_structure="Large rounded head drawn with restrained continuous contour lines",
        head_body_relationship="Head remains visually dominant over the compact body",
        ear_structure="Paired short rounded ears attached at stable side-head positions",
        eye_structure="Two small wide-set eyes aligned on a restrained facial axis",
        nose_mouth="Tiny centered nose and minimal mouth below the eye axis",
        limb_structure="Short graphic limbs that can articulate without realistic anatomy",
        body_proportions="Head-dominant proportions, compact torso, and short limbs",
        pose="Original reference pose; observational evidence rather than a frozen template",
        line_language="Clean dark minimal contours, rounded turns, and no fur rendering",
        immutable_features=[
            "facial relational geometry",
            "short rounded ear grammar",
            "head-dominant proportion signature",
            "minimal contour language",
        ],
        mutable_features=[
            "pose",
            "viewpoint",
            "limb position",
            "body orientation",
            "expression within facial grammar",
            "clothing and held objects",
        ],
        identity_risks=[
            "large anime eyes",
            "realistic canine muzzle or fur",
            "oversized plush ears",
            "generic cartoon redesign",
        ],
        facial_relationships="Wide-set small eyes above a centered minimal nose-mouth unit",
        recognition_markers=[
            "head-dominant proportion",
            "short rounded ears",
            "small wide-set eyes",
            "minimal centered nose-mouth",
        ],
        confidence=0.92,
    )
    grammar = IPIdentityGrammar(
        character_type=ip_dna.character_type,
        core_identity_anchors=[
            "small wide-set eyes with a centered minimal nose-mouth",
            "short rounded paired ears",
            "head-dominant compact proportions",
            "clean minimal dark contour language",
        ],
        relational_geometry=[
            "eyes remain wide-set on one facial axis",
            "nose-mouth remains centered below the eyes",
            "ears retain their characteristic attachment relative to the head",
        ],
        structural_topology=[
            "one large head connected to one compact torso",
            "paired simplified ears and paired simplified limbs",
        ],
        proportion_signature=[
            "head remains larger than the torso",
            "limbs remain short and graphically simplified",
        ],
        line_style_grammar=[
            "clean minimal dark contours",
            "rounded turns",
            "no realistic fur, shading, or 3D rendering",
        ],
        facial_grammar=[
            "small wide-set eyes",
            "tiny centered nose",
            "restrained mouth mark",
        ],
        ear_grammar=["short rounded paired ears; never large furry hanging ears"],
        limb_grammar=["short simplified limbs may bend without realistic anatomy"],
        deformable_features=["limb articulation", "body axis", "visible overlap"],
        pose_transformation_rules=[
            "sitting and waving are legal when identity anchors remain consistent",
            "reconstruct limb overlap and body balance for the target action",
        ],
        viewpoint_transformation_rules=[
            "front, side, and three-quarter views are legal",
            "project facial and ear relationships consistently for the selected view",
        ],
        expression_rules=["expression may change within the minimal facial grammar"],
        accessory_attachment_rules=[
            "headwear sits above the head without replacing the ears",
            "held objects may cover one limb but not the core face",
        ],
        clothing_adaptation_rules=[
            "clothing follows the reconstructed torso and limb pose",
            "brand graphics remain applications rather than replacement anatomy",
        ],
        occlusion_rules=["keep the face, ear grammar, and proportion anchors recognizable"],
        immutable_features=list(ip_dna.immutable_features),
        mutable_features=list(ip_dna.mutable_features),
        pose_dependent_features=[
            "silhouette projection",
            "limb position",
            "body orientation",
            "visible torso length",
        ],
        forbidden_drift=list(ip_dna.identity_risks),
        identity_risks=list(ip_dna.identity_risks),
        unknowns=[],
        confidence=0.92,
    )
    return IPIntelligenceResult(ip_dna=ip_dna, identity_grammar=grammar)


def brand_fixture() -> BrandFeaturePool:
    feature = BrandFeature(
        feature_id="demo-product-01",
        name="small branded product",
        category="product",
        description="A compact product cue that supports holding and serving behavior.",
        recognition_strength=85,
        evidence=["Packaged demo brand reference"],
        integration_affordances=["held_object", "product_interaction", "role"],
        preferred_uses=["held object", "offering gesture", "service behavior"],
        secondary_uses=["table prop"],
        avoid_uses=["replace the face", "replace ear structure"],
        interaction_modes=["hold", "offer", "serve"],
        attachment_targets=["left limb", "nearby surface"],
        scale_guidance="Keep subordinate to the character face and gesture.",
        occlusion_risk="Do not cover the core face or both action limbs.",
        identity_conflict_risk="Low when treated as a held object.",
    )
    return BrandFeaturePool(
        brand_name="Demo brand shown in reference",
        logo_features=["small graphic mark"],
        color_palette=["red accent", "yellow accent"],
        product_elements=["small branded product"],
        scene_elements=["light service context"],
        collaboration_patterns=["character role plus product interaction"],
        evidence=["Packaged demo brand reference"],
        features=[feature],
        organic_fusion_guidance=[
            "Use product interaction and role instead of a floating logo sticker."
        ],
    )


def brief_fixture() -> CreativeBrief:
    return CreativeBrief(
        theme_name="Friendly wave and product greeting",
        objective="Re-pose the original IP into a seated greeting role.",
        priority_stack=[
            "User free text: sit and wave",
            "Preserve IP Identity Grammar",
            "Use organic product interaction",
        ],
        must_include=["seated pose", "right-limb wave", "small held product"],
        must_preserve=["facial grammar", "ear grammar", "proportion signature"],
        creative_direction="A recognizable seated mascot waves while presenting a product.",
        evidence=["Explicit smoke target: sitting and waving"],
        desired_character_role="friendly brand greeter",
        desired_action="sit and wave with the right limb while presenting a product",
        desired_interaction="hold a small product in the left limb as part of the greeting",
        desired_view="clear three-quarter view",
        transformation_level=TransformationLevel.HIGH,
    )


def strategy_fixture() -> FusionStrategy:
    relationship = FusionRelationship(
        ip_role="recognizable friendly greeter",
        brand_role="product and service context",
        interaction="the seated character waves while presenting the product",
        behavior="friendly right-limb wave",
        product_interaction="left limb holds and presents a small product",
        apparel_integration="simple fitted service apron",
        graphic_integration="one small mark on the apron",
        color_integration="controlled red and yellow accents",
        scene_integration="minimal service counter cue",
        narrative="the original character welcomes the viewer as a friendly greeter",
        fusion_depth=FusionDepth.PRODUCT_INTERACTION,
    )
    return FusionStrategy(
        theme_name="Friendly wave and product greeting",
        fusion_logic="Behavior and product interaction lead; graphics remain secondary.",
        clothing=["simple fitted service apron"],
        headwear=["small red service cap"],
        brand_accessories=["one small apron mark"],
        held_items=["small branded product"],
        scene=["minimal service counter cue"],
        palette=["controlled red accent", "controlled yellow accent"],
        design_tags=["seated greeting", "product interaction", "organic fusion"],
        generation_prompt="Re-pose the recognizable IP into a seated waving greeter.",
        negative_prompt="No realistic fur, generic cartoon redesign, or floating logo sticker.",
        fusion_relationship=relationship,
    )


def adaptation_fixture(
    intelligence: IPIntelligenceResult | None = None,
) -> IPAdaptationPlan:
    """Deterministic plan used by the separate Guardian smoke."""

    intelligence = intelligence or identity_fixture()
    grammar = intelligence.identity_grammar
    assert grammar is not None
    strategy = strategy_fixture()
    return IPAdaptationPlan(
        target_action="sit and wave with the right limb while presenting a product",
        target_pose="balanced seated pose with an open right-limb wave",
        view_angle="clear three-quarter view",
        transformation_level=TransformationLevel.HIGH,
        pose_blueprint=PoseBlueprint(
            head_orientation="turn gently toward the viewer",
            body_axis="upright seated axis with stable balance",
            left_limb="hold the small product near the torso",
            right_limb="lift outward in a readable wave",
            legs="fold into a simple balanced seated base",
            tail_if_applicable="project consistently or omit if not applicable",
            ear_behavior="follow head turn while keeping short rounded attachments",
            facial_projection="preserve eye and nose-mouth relationships in three-quarter view",
        ),
        deformation_map=DeformationMap(
            preserve=list(grammar.core_identity_anchors),
            transform=["pose", "viewpoint", "limb position", "body orientation"],
            pose_dependent=list(grammar.pose_dependent_features),
            forbidden=list(grammar.forbidden_drift),
        ),
        identity_preservation=IdentityPreservationPlan(
            anchors_to_preserve=list(grammar.core_identity_anchors),
            relational_rules=list(grammar.relational_geometry),
            proportion_rules=list(grammar.proportion_signature),
            facial_rules=list(grammar.facial_grammar),
            line_style_rules=list(grammar.line_style_grammar),
        ),
        brand_attachment=BrandAttachmentPlan(
            clothing=list(strategy.clothing),
            headwear=list(strategy.headwear),
            held_objects=list(strategy.held_items),
            logo_application=list(strategy.brand_accessories),
            color_application=list(strategy.palette),
        ),
        interaction_plan=InteractionPlan(
            product_interaction=strategy.fusion_relationship.product_interaction,
            environment_interaction=strategy.fusion_relationship.scene_integration,
            behavior=strategy.fusion_relationship.behavior,
        ),
        occlusion_rules=list(grammar.occlusion_rules),
        attachment_rules=[
            *grammar.accessory_attachment_rules,
            *grammar.clothing_adaptation_rules,
        ],
        generation_instructions=[
            "Use the original image as an identity reference, not a frozen pose template.",
            "Re-pose the character explicitly into a seated waving action.",
            "Do not simply overlay brand assets on the original pose.",
        ],
        negative_constraints=list(grammar.forbidden_drift),
    )


def smoke_assets() -> InputAssets:
    return InputAssets(
        ip_image=str(IP_REFERENCE),
        brand_image=str(BRAND_REFERENCE),
        ip_filename=IP_REFERENCE.name,
        brand_filename=BRAND_REFERENCE.name,
        brand_name="Demo brand shown in reference",
    )


def smoke_intent() -> UserIntent:
    return UserIntent(
        selected_goals=["产品元素", "服装融合"],
        goal_text="让原IP改成坐姿，右手挥手，左手自然拿着品牌产品；不要冻结原姿势。",
    )


def upstream_outputs() -> dict[str, dict[str, Any]]:
    return {
        AgentNames.IP_INTELLIGENCE: identity_fixture().model_dump(mode="json"),
        AgentNames.BRAND_FEATURE: brand_fixture().model_dump(mode="json"),
        AgentNames.CREATIVE_BRIEF: brief_fixture().model_dump(mode="json"),
        AgentNames.FUSION_DECISION: strategy_fixture().model_dump(mode="json"),
    }


def _validate_adaptation(plan: IPAdaptationPlan) -> None:
    if plan.transformation_level != TransformationLevel.HIGH:
        raise AssertionError("Terra did not preserve the requested HIGH transformation level")
    if not all(
        (
            plan.target_action.strip(),
            plan.target_pose.strip(),
            plan.view_angle.strip(),
            plan.pose_blueprint.head_orientation.strip(),
            plan.pose_blueprint.body_axis.strip(),
            plan.identity_preservation.anchors_to_preserve,
            plan.deformation_map.transform,
            plan.generation_instructions,
        )
    ):
        raise AssertionError("Terra returned an incomplete IPAdaptationPlan")
    target = f"{plan.target_action} {plan.target_pose}".casefold()
    if not any(marker in target for marker in ("sit", "seated", "坐")):
        raise AssertionError("Terra omitted the requested seated pose")
    if not any(marker in target for marker in ("wave", "waving", "挥手")):
        raise AssertionError("Terra omitted the requested waving action")
    if not plan.brand_attachment.held_objects or not plan.interaction_plan.product_interaction:
        raise AssertionError("Terra omitted the requested product interaction")
    frozen_phrases = (
        "保持原始姿势",
        "保持原姿势",
        "keep original pose",
        "keep the original pose",
        "exact original pose",
    )
    joined = " ".join(plan.generation_instructions).casefold()
    if any(phrase in joined for phrase in frozen_phrases):
        raise AssertionError("Terra froze the original pose despite an explicit re-pose target")
    if "re-pose the character explicitly" not in joined:
        raise AssertionError("HIGH transformation plan omitted the explicit re-pose instruction")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    if not IP_REFERENCE.is_file() or not BRAND_REFERENCE.is_file():
        print("SKIP: packaged demo reference assets are unavailable")
        return 0
    try:
        loaded = load_real_terra()
    except Exception as exc:
        print(f"FAIL: Terra provider setup ({type(exc).__name__})")
        return 1
    if loaded is None:
        return 0
    settings, provider = loaded
    before = len(getattr(provider.provider_client, "records", ()))
    context = AgentContext(
        run_id="ip-adaptation-smoke",
        input_assets=smoke_assets(),
        user_intent=smoke_intent(),
        outputs=upstream_outputs(),
    )
    try:
        plan = IPAdaptationAgent(ai_provider=provider).process(context).output
        _validate_adaptation(plan)
        logical_calls = len(getattr(provider.provider_client, "records", ())) - before
        if logical_calls != 1:
            raise AssertionError("IP Adaptation smoke must make exactly one logical Terra call")
    except Exception as exc:
        print(f"FAIL: Terra IP Adaptation smoke ({type(exc).__name__})")
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "model": settings.model_main,
                "logical_terra_calls": 1,
                "gpt_image_2_calls": 0,
                "target": "seated pose with right-limb wave and product interaction",
                "ip_adaptation_plan": plan.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
