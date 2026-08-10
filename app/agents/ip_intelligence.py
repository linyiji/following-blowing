"""Extract IP DNA and the pose-aware identity grammar."""

from __future__ import annotations

from app.schemas import IPAsset, IPDNA, IPIdentityGrammar, IPIntelligenceResult
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class IPIntelligenceAgent(BaseAgent[IPIntelligenceResult]):
    name = AgentNames.IP_INTELLIGENCE
    prompt_id = "ip_intelligence"
    responsibility = (
        "Explain why the character remains itself across pose, viewpoint, and interaction changes."
    )
    handoff = "IP DNA + IP Identity Grammar → Creative Brief, Adaptation, and Guardian"

    def input_summary(self, context: AgentContext) -> str:
        asset = context.require_output(AgentNames.IP_PREPARATION, IPAsset)
        return f"Analyze normalized IP asset: {asset.filename or 'inline image'}"

    def process(self, context: AgentContext) -> AgentDecision[IPIntelligenceResult]:
        asset = context.require_output(AgentNames.IP_PREPARATION, IPAsset)
        if self.ai_provider is None:
            raise RuntimeError("IP Intelligence requires an AI provider")

        ip_dna = IPDNA(
            character_type="Rounded minimal line-art mascot character",
            full_body_structure="Compact body topology with a head-dominant design and simplified limbs",
            silhouette="Rounded character envelope whose projected outline may change naturally by pose",
            head_structure="Large rounded head built from a restrained continuous contour",
            head_body_relationship="Head remains dominant relative to a compact torso across poses",
            ear_structure="Paired short rounded ears attached at characteristic side-head positions",
            eye_structure="Two small wide-set eyes on a stable facial axis",
            nose_mouth="Small centered nose with a restrained mouth relationship",
            limb_structure="Short simplified limbs that may articulate without becoming realistic anatomy",
            body_proportions="Large head, compact torso, short simplified limbs",
            pose="Reference pose is observational evidence, not an immutable template",
            line_language="Clean dark minimal contours with rounded turns and no realistic fur rendering",
            immutable_features=[
                "facial relational geometry",
                "ear grammar",
                "head-to-body proportion signature",
                "minimal line-style grammar",
                "character species and topology",
            ],
            mutable_features=[
                "pose",
                "viewpoint",
                "limb position",
                "body orientation",
                "expression within facial grammar",
                "clothing and accessories",
            ],
            identity_risks=[
                "large anime eyes",
                "realistic canine muzzle or fur",
                "oversized plush ears",
                "destruction of the head-to-body ratio",
                "generic cartoonization",
            ],
            facial_relationships="Wide-set small eyes above a centered minimal nose-mouth unit",
            recognition_markers=[
                "head-dominant proportion",
                "paired short rounded ears",
                "small wide-set eyes and centered minimal nose-mouth",
                "minimal contour language",
            ],
            confidence=0.92,
        )
        grammar = IPIdentityGrammar(
            character_type=ip_dna.character_type,
            core_identity_anchors=[
                "small wide-set eyes with centered minimal nose-mouth",
                "short rounded ear grammar",
                "head-dominant compact proportion signature",
                "minimal black contour language",
                "simplified mascot topology",
            ],
            relational_geometry=[
                "eyes remain wide-set on the same facial axis",
                "nose-mouth unit remains centered below the eyes",
                "ears retain characteristic attachment relative to the head",
            ],
            structural_topology=[
                "one large head connected to a compact torso",
                "paired simplified ears and paired simplified limbs",
            ],
            proportion_signature=[
                "head remains visually larger than the torso",
                "limbs remain short and graphically simplified",
            ],
            line_style_grammar=[
                "clean minimal dark contours",
                "rounded turns",
                "no realistic fur texture or 3D rendering",
            ],
            facial_grammar=[
                "small wide-set eyes",
                "centered tiny nose",
                "restrained mouth mark",
            ],
            ear_grammar=["short rounded paired ears; never oversized furry hanging ears"],
            limb_grammar=["short simplified limbs may bend and move without realistic anatomy"],
            deformable_features=["limb articulation", "body axis", "visible overlap", "expression"],
            pose_transformation_rules=[
                "sitting, standing, running, waving, holding, hugging, or turning are legal",
                "reconstruct overlaps and limb positions for the target action",
            ],
            viewpoint_transformation_rules=[
                "front, side, and three-quarter views are legal",
                "project facial and ear relationships consistently for the selected view",
            ],
            expression_rules=["vary expression only within the small-eye minimal-mouth grammar"],
            accessory_attachment_rules=[
                "attach headwear above the head without replacing ears",
                "held objects may occlude a limb but not erase core face recognition",
            ],
            clothing_adaptation_rules=[
                "clothing follows the new torso and limb pose",
                "logos remain secondary applications rather than replacement anatomy",
            ],
            occlusion_rules=["keep enough face, ear, and proportion anchors visible for recognition"],
            immutable_features=list(ip_dna.immutable_features),
            mutable_features=list(ip_dna.mutable_features),
            pose_dependent_features=[
                "silhouette projection",
                "limb position",
                "body orientation",
                "ear overlap",
                "visible torso length",
            ],
            forbidden_drift=list(ip_dna.identity_risks),
            identity_risks=list(ip_dna.identity_risks),
            unknowns=[],
            confidence=0.92,
        )
        demo_output = IPIntelligenceResult(ip_dna=ip_dna, identity_grammar=grammar)
        output = self.ai_provider.analyze_multimodal(
            images=[asset.normalized_uri],
            prompt=self.prompt_text,
            response_model=IPIntelligenceResult,
            model_role="main",
            demo_output=demo_output.model_dump(mode="json"),
        )
        if not isinstance(output, IPIntelligenceResult):
            output = IPIntelligenceResult.model_validate(output)
        assert output.identity_grammar is not None
        return AgentDecision(
            output=output,
            decision_summary=(
                "Terra Vision separated stable identity rules from pose-dependent and deformable "
                "features; the reference pose is not frozen."
            ),
            output_summary="Terra Vision IP DNA and IP Identity Grammar created.",
            evidence=tuple(output.identity_grammar.core_identity_anchors),
        )
