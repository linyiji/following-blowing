"""Pydantic schemas shared by the workflow, agents, and Streamlit UI.

The workflow persists these models as JSON-compatible checkpoints.  Agent outputs
therefore deliberately contain references to binary assets instead of embedding
provider clients or other process-local objects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from math import isclose
from typing import Any, ClassVar, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return a timezone-aware timestamp suitable for audit records."""

    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    """Base model for checkpoint-safe workflow data."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AgentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GuardianVerdict(str, Enum):
    REJECT = "REJECT"
    REVISE = "REVISE"
    PASS = "PASS"


ALLOWED_GOALS: tuple[str, ...] = (
    "服装融合",
    "帽子 / 头饰",
    "品牌Logo",
    "品牌配色",
    "产品元素",
    "场景融合",
    "联名故事",
    "周边应用",
)


RANKING_WEIGHTS: dict[str, float] = {
    "user_goal_match": 0.25,
    "ip_identity_consistency": 0.25,
    "brand_recognition": 0.15,
    "fusion_naturalness": 0.15,
    "commercial_value": 0.10,
    "historical_collaboration_reference": 0.05,
    "innovation": 0.05,
}


GUARDIAN_IDENTITY_WEIGHTS: dict[str, int] = {
    "original_ip_recognition": 25,
    "identity_anchor_consistency": 20,
    "facial_relationship_consistency": 15,
    "structural_grammar_consistency": 15,
    "proportion_signature_consistency": 10,
    "line_style_grammar_consistency": 10,
    "valid_pose_deformation": 5,
}

GUARDIAN_COMPLIANCE_GATES: tuple[str, ...] = (
    "target_pose_compliance",
    "user_intent_compliance",
    "brand_integration_compliance",
)

GUARDIAN_REQUIRED_CHECKS: tuple[str, ...] = (
    *GUARDIAN_IDENTITY_WEIGHTS,
    *GUARDIAN_COMPLIANCE_GATES,
)

# Checkpoints produced before IP Identity Grammar used this score contract. It
# remains explicit so historical ``terra_python_v2`` Guardian records can be
# read without silently reinterpreting their numbers under the new formula.
LEGACY_GUARDIAN_IDENTITY_WEIGHTS: dict[str, int] = {
    "original_ip_recognition": 20,
    "silhouette": 15,
    "head_body_structure": 15,
    "ear_structure": 10,
    "eye_structure": 10,
    "nose_mouth": 10,
    "body_proportions": 10,
    "line_language": 10,
}

LEGACY_GUARDIAN_REQUIRED_CHECKS: tuple[str, ...] = (
    *LEGACY_GUARDIAN_IDENTITY_WEIGHTS,
    "user_intent_constraints",
)


class InputAssets(StrictModel):
    """References to the two user-provided source images."""

    ip_image: str = Field(min_length=1)
    brand_image: str = Field(min_length=1)
    ip_filename: str | None = None
    brand_filename: str | None = None
    brand_name: str = Field(default="麦当劳", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserIntent(StrictModel):
    """User intent with explicit adoption state for optional AI suggestions."""

    selected_goals: list[str] = Field(default_factory=list)
    goal_text: str = ""
    ai_suggestion: str | dict[str, Any] | None = None
    ai_suggestion_adopted: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("selected_goals")
    @classmethod
    def validate_goals(cls, goals: list[str]) -> list[str]:
        unknown = [goal for goal in goals if goal not in ALLOWED_GOALS]
        if unknown:
            raise ValueError(f"Unsupported collaboration goals: {unknown}")
        # Preserve UI order while preventing accidental duplicate constraints.
        return list(dict.fromkeys(goals))

    @field_validator("goal_text")
    @classmethod
    def strip_goal_text(cls, value: str) -> str:
        return value.strip()

    def adopted_suggestion_text(self) -> str | None:
        if not self.ai_suggestion_adopted or self.ai_suggestion is None:
            return None
        if isinstance(self.ai_suggestion, str):
            return self.ai_suggestion.strip() or None
        return "; ".join(f"{key}: {value}" for key, value in self.ai_suggestion.items())

    def prioritized_constraints(self) -> list[str]:
        """Return constraints in the mandated user text > selection > AI order."""

        constraints: list[str] = []
        if self.goal_text:
            constraints.append(self.goal_text)
        constraints.extend(self.selected_goals)
        suggestion = self.adopted_suggestion_text()
        if suggestion:
            constraints.append(suggestion)
        return constraints


class IPAsset(StrictModel):
    source_uri: str = Field(min_length=1)
    normalized_uri: str = Field(min_length=1)
    filename: str | None = None
    mime_type: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    sha256: str | None = None
    preparation_notes: list[str] = Field(default_factory=list)


class IPDNA(StrictModel):
    character_type: str
    full_body_structure: str
    silhouette: str
    head_structure: str
    head_body_relationship: str
    ear_structure: str
    eye_structure: str
    nose_mouth: str
    limb_structure: str
    body_proportions: str
    pose: str
    line_language: str
    immutable_features: list[str]
    mutable_features: list[str]
    identity_risks: list[str]

    # Retained so checkpoints created by the original demo remain readable.
    facial_relationships: str = ""
    recognition_markers: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_ip_dna(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        facial = str(data.get("facial_relationships", ""))
        markers = list(data.get("recognition_markers", []) or [])
        data.setdefault("character_type", "Legacy checkpoint: character type not recorded")
        data.setdefault("full_body_structure", str(data.get("body_proportions", "")))
        data.setdefault(
            "head_body_relationship",
            "; ".join(
                item
                for item in (
                    str(data.get("head_structure", "")),
                    str(data.get("body_proportions", "")),
                )
                if item
            ),
        )
        data.setdefault("eye_structure", facial)
        data.setdefault("nose_mouth", facial)
        data.setdefault("limb_structure", str(data.get("body_proportions", "")))
        data.setdefault("pose", "Legacy checkpoint: pose not recorded")
        data.setdefault("immutable_features", markers)
        data.setdefault("mutable_features", [])
        data.setdefault("identity_risks", [])
        return data


class IdentityLock(StrictModel):
    """Deprecated compatibility projection of :class:`IPIdentityGrammar`.

    New agents reason from ``IPIdentityGrammar``.  The compact lock remains in
    checkpoints and exports so schema-v1 runs and downstream integrations can
    still be inspected safely.
    """

    locked_features: list[str]
    allowed_changes: list[str]
    forbidden_changes: list[str]
    recognition_rule: str


class IPIdentityGrammar(StrictModel):
    """Rules that keep a character recognizable across legitimate changes."""

    character_type: str
    core_identity_anchors: list[str]
    relational_geometry: list[str]
    structural_topology: list[str]
    proportion_signature: list[str]
    line_style_grammar: list[str]
    facial_grammar: list[str]
    ear_grammar: list[str]
    limb_grammar: list[str]
    deformable_features: list[str]
    pose_transformation_rules: list[str]
    viewpoint_transformation_rules: list[str]
    expression_rules: list[str]
    accessory_attachment_rules: list[str]
    clothing_adaptation_rules: list[str]
    occlusion_rules: list[str]
    immutable_features: list[str]
    mutable_features: list[str]
    pose_dependent_features: list[str]
    forbidden_drift: list[str]
    identity_risks: list[str]
    unknowns: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)

    @classmethod
    def from_legacy(cls, ip_dna: IPDNA, lock: IdentityLock) -> "IPIdentityGrammar":
        """Project a schema-v1 lock into a readable compatibility grammar.

        This projection is never treated as a completed v2 intelligence result;
        WorkflowEngine invalidates legacy checkpoints from IP Intelligence
        downstream so Terra can produce a native grammar before new work runs.
        """

        return cls(
            character_type=ip_dna.character_type,
            core_identity_anchors=list(
                dict.fromkeys([*lock.locked_features, *ip_dna.immutable_features])
            ),
            relational_geometry=[
                item
                for item in (
                    ip_dna.head_body_relationship,
                    ip_dna.facial_relationships,
                    ip_dna.nose_mouth,
                )
                if item
            ],
            structural_topology=[
                ip_dna.full_body_structure,
                ip_dna.head_structure,
                ip_dna.limb_structure,
            ],
            proportion_signature=[ip_dna.body_proportions],
            line_style_grammar=[ip_dna.line_language],
            facial_grammar=[ip_dna.eye_structure, ip_dna.nose_mouth],
            ear_grammar=[ip_dna.ear_structure],
            limb_grammar=[ip_dna.limb_structure],
            deformable_features=list(lock.allowed_changes),
            pose_transformation_rules=[
                "Pose may change when identity anchors and relational geometry remain valid."
            ],
            viewpoint_transformation_rules=[
                "Viewpoint may change while preserving characteristic feature relationships."
            ],
            expression_rules=[
                "Expression may vary without redesigning the eye or nose-mouth grammar."
            ],
            accessory_attachment_rules=[
                "Attach accessories without replacing core facial or ear structures."
            ],
            clothing_adaptation_rules=[
                "Adapt clothing to the new pose without replacing body topology."
            ],
            occlusion_rules=[
                "Do not occlude enough identity anchors to prevent recognition."
            ],
            immutable_features=list(lock.locked_features),
            mutable_features=list(lock.allowed_changes),
            pose_dependent_features=["limb position", "body orientation", "visible overlap"],
            forbidden_drift=list(lock.forbidden_changes),
            identity_risks=list(ip_dna.identity_risks),
            unknowns=["Compatibility projection from schema-v1 IdentityLock"],
            confidence=min(ip_dna.confidence, 0.5),
        )

    def compatibility_lock(self) -> IdentityLock:
        """Return the deprecated compact lock without freezing pose or viewpoint."""

        return IdentityLock(
            locked_features=list(self.core_identity_anchors),
            allowed_changes=list(
                dict.fromkeys(
                    [
                        *self.mutable_features,
                        *self.deformable_features,
                        *self.pose_dependent_features,
                        "pose",
                        "viewpoint",
                        "limb position",
                        "body orientation",
                    ]
                )
            ),
            forbidden_changes=list(self.forbidden_drift),
            recognition_rule=(
                "The character may change pose, viewpoint, clothing, and interaction while "
                "preserving its identity anchors, relational geometry, proportion signature, "
                "facial grammar, ear grammar, and line-style grammar."
            ),
        )


class IPIntelligenceResult(StrictModel):
    ip_dna: IPDNA
    identity_grammar: IPIdentityGrammar | None = None
    identity_lock: IdentityLock | None = None

    @model_validator(mode="after")
    def ensure_identity_grammar_and_compatibility_lock(self) -> "IPIntelligenceResult":
        grammar = self.identity_grammar
        lock = self.identity_lock
        if grammar is None and lock is None:
            raise ValueError("IP Intelligence requires identity_grammar or identity_lock")
        if grammar is None and lock is not None:
            grammar = IPIdentityGrammar.from_legacy(self.ip_dna, lock)
            object.__setattr__(self, "identity_grammar", grammar)
        if lock is None and grammar is not None:
            object.__setattr__(self, "identity_lock", grammar.compatibility_lock())
        return self


class SearchResult(StrictModel):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    source: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class BrandProfile(StrictModel):
    brand_name: str
    brand_summary: str
    logo_features: list[str]
    color_palette: list[str]
    product_elements: list[str]
    visual_language: list[str]
    evidence: list[str] = Field(default_factory=list)


class CollaborationResearch(StrictModel):
    brand_name: str
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    evidence_gap: bool = False
    warnings: list[str] = Field(default_factory=list)
    search_mode: Literal["demo", "live", "unverified"] = "unverified"
    research_label: str = "Unverified Search Capability"


class CollaborationResearchReasoning(StrictModel):
    patterns: list[str] = Field(default_factory=list)
    rationale: str
    evidence_used: list[str] = Field(default_factory=list)
    evidence_gap: bool


BrandIntegrationMode = Literal[
    "apparel",
    "accessory",
    "held_object",
    "product_interaction",
    "role",
    "environment",
    "narrative",
    "graphic_application",
    "color_application",
]


class BrandFeature(StrictModel):
    """One evidenced brand cue plus safe ways to integrate it organically."""

    feature_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    recognition_strength: float = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    integration_affordances: list[BrandIntegrationMode] = Field(default_factory=list)
    preferred_uses: list[str] = Field(default_factory=list)
    secondary_uses: list[str] = Field(default_factory=list)
    avoid_uses: list[str] = Field(default_factory=list)
    interaction_modes: list[str] = Field(default_factory=list)
    attachment_targets: list[str] = Field(default_factory=list)
    scale_guidance: str = ""
    occlusion_risk: str = ""
    identity_conflict_risk: str = ""


class BrandFeaturePool(StrictModel):
    brand_name: str
    logo_features: list[str]
    color_palette: list[str]
    product_elements: list[str]
    scene_elements: list[str]
    collaboration_patterns: list[str]
    evidence: list[str] = Field(default_factory=list)
    features: list[BrandFeature] = Field(default_factory=list)
    organic_fusion_guidance: list[str] = Field(default_factory=list)


class TransformationLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CreativeBrief(StrictModel):
    theme_name: str
    objective: str
    priority_stack: list[str]
    must_include: list[str]
    must_preserve: list[str]
    creative_direction: str
    ai_contribution: str | None = None
    evidence: list[str] = Field(default_factory=list)
    desired_character_role: str = "collaboration character"
    desired_action: str = "natural brand-relevant action"
    desired_interaction: str = "organic interaction with selected brand cues"
    desired_view: str = "best view for the requested action"
    transformation_level: TransformationLevel = TransformationLevel.MEDIUM


class FusionDepth(str, Enum):
    STICKER = "STICKER"
    COLOR = "COLOR"
    ACCESSORY = "ACCESSORY"
    APPAREL = "APPAREL"
    PRODUCT_INTERACTION = "PRODUCT_INTERACTION"
    BEHAVIOR = "BEHAVIOR"
    ROLE = "ROLE"
    NARRATIVE = "NARRATIVE"


class FusionRelationship(StrictModel):
    ip_role: str = "recognizable collaboration character"
    brand_role: str = "brand context and interaction partner"
    interaction: str = "brand cue integration"
    behavior: str = "character performs a brand-relevant action"
    product_interaction: str = ""
    apparel_integration: str = ""
    graphic_integration: str = ""
    color_integration: str = ""
    scene_integration: str = ""
    narrative: str = ""
    fusion_depth: FusionDepth = FusionDepth.STICKER


class FusionStrategy(StrictModel):
    theme_name: str
    fusion_logic: str
    clothing: list[str] = Field(default_factory=list)
    headwear: list[str] = Field(default_factory=list)
    brand_accessories: list[str] = Field(default_factory=list)
    held_items: list[str] = Field(default_factory=list)
    scene: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    design_tags: list[str] = Field(default_factory=list)
    generation_prompt: str
    negative_prompt: str
    fusion_relationship: FusionRelationship = Field(default_factory=FusionRelationship)


class PoseBlueprint(StrictModel):
    head_orientation: str
    body_axis: str
    left_limb: str
    right_limb: str
    legs: str
    tail_if_applicable: str
    ear_behavior: str
    facial_projection: str


class DeformationMap(StrictModel):
    preserve: list[str]
    transform: list[str]
    pose_dependent: list[str]
    forbidden: list[str]


class IdentityPreservationPlan(StrictModel):
    anchors_to_preserve: list[str]
    relational_rules: list[str]
    proportion_rules: list[str]
    facial_rules: list[str]
    line_style_rules: list[str]


class BrandAttachmentPlan(StrictModel):
    clothing: list[str]
    headwear: list[str]
    held_objects: list[str]
    logo_application: list[str]
    color_application: list[str]


class InteractionPlan(StrictModel):
    product_interaction: str
    environment_interaction: str
    behavior: str


class IPAdaptationPlan(StrictModel):
    """Pose-aware plan between Fusion Decision and image generation."""

    target_action: str
    target_pose: str
    view_angle: str
    transformation_level: TransformationLevel
    pose_blueprint: PoseBlueprint
    deformation_map: DeformationMap
    identity_preservation: IdentityPreservationPlan
    brand_attachment: BrandAttachmentPlan
    interaction_plan: InteractionPlan
    occlusion_rules: list[str]
    attachment_rules: list[str]
    generation_instructions: list[str]
    negative_constraints: list[str]


class CandidateDesign(StrictModel):
    candidate_id: str
    image_uri: str = Field(min_length=1)
    theme_name: str
    fusion_logic: str
    design_tags: list[str]
    generation_prompt: str
    revision_number: int = Field(default=0, ge=0)
    # Deprecated input-only compatibility for old checkpoints. New candidates do
    # not serialize or consume model-invented Guardian metrics.
    guardian_metrics: dict[str, float] = Field(default_factory=dict, exclude=True)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("guardian_metrics")
    @classmethod
    def validate_guardian_metrics(cls, metrics: dict[str, float]) -> dict[str, float]:
        invalid = {key: value for key, value in metrics.items() if not 0 <= value <= 100}
        if invalid:
            raise ValueError(f"Guardian metrics must be between 0 and 100: {invalid}")
        return metrics


class GuardianResult(StrictModel):
    candidate_id: str
    identity_score: float = Field(ge=0, le=100)
    score: float = Field(ge=0, le=100)
    verdict: GuardianVerdict
    checks: dict[str, float]
    check_reasons: dict[str, str] = Field(default_factory=dict)
    major_differences: list[str] = Field(default_factory=list)
    preserve: list[str] = Field(default_factory=list)
    change_only: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    intent_constraints_met: bool
    target_pose_compliance: float | None = Field(default=None, ge=0, le=100)
    user_intent_compliance: float | None = Field(default=None, ge=0, le=100)
    brand_integration_compliance: float | None = Field(default=None, ge=0, le=100)
    original_pose: str = ""
    target_pose: str = ""
    candidate_pose: str = ""
    allowed_transformations: list[str] = Field(default_factory=list)
    identity_drift: list[str] = Field(default_factory=list)
    forbidden_drift_detected: bool = False
    severe_forbidden_drift: bool = False
    identity_corrections: list[str] = Field(default_factory=list)
    pose_corrections: list[str] = Field(default_factory=list)
    brand_corrections: list[str] = Field(default_factory=list)
    style_corrections: list[str] = Field(default_factory=list)
    revision_instruction: str | None = None
    retry_count: int = Field(default=0, ge=0)
    scoring_version: str = "legacy_v1"

    @model_validator(mode="before")
    @classmethod
    def keep_score_alias_compatible(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        if "identity_score" not in data and "score" in data:
            data["identity_score"] = data["score"]
        if "score" not in data and "identity_score" in data:
            data["score"] = data["identity_score"]
        checks = data.get("checks")
        if isinstance(checks, Mapping):
            data.setdefault("target_pose_compliance", checks.get("target_pose_compliance"))
            data.setdefault("user_intent_compliance", checks.get("user_intent_compliance"))
            data.setdefault(
                "brand_integration_compliance", checks.get("brand_integration_compliance")
            )
        return data

    @field_validator("checks")
    @classmethod
    def validate_checks(cls, checks: dict[str, float]) -> dict[str, float]:
        if not checks:
            raise ValueError("Guardian checks cannot be empty")
        invalid = {key: value for key, value in checks.items() if not 0 <= value <= 100}
        if invalid:
            raise ValueError(f"Guardian checks must be between 0 and 100: {invalid}")
        return checks

    @model_validator(mode="after")
    def validate_threshold_contract(self) -> "GuardianResult":
        if not isclose(self.score, self.identity_score, abs_tol=0.01):
            raise ValueError("score must equal the canonical identity_score")
        if self.scoring_version == "pose_aware_grammar_v3":
            missing = set(GUARDIAN_REQUIRED_CHECKS) - set(self.checks)
            if missing:
                raise ValueError(f"Guardian checks are missing required keys: {sorted(missing)}")
            expected_score = calculate_guardian_identity_score(self.checks)
            if not isclose(self.identity_score, expected_score, abs_tol=0.01):
                raise ValueError(
                    f"identity_score must be the Python weighted result {expected_score}"
                )
            missing_reasons = set(GUARDIAN_REQUIRED_CHECKS) - set(self.check_reasons)
            if missing_reasons:
                raise ValueError(
                    "Guardian check reasons are missing required keys: "
                    f"{sorted(missing_reasons)}"
                )
            for gate in GUARDIAN_COMPLIANCE_GATES:
                explicit = getattr(self, gate)
                if explicit is None or not isclose(
                    explicit, float(self.checks[gate]), abs_tol=0.01
                ):
                    raise ValueError(f"{gate} must equal the corresponding Terra check")
            expected = guardian_verdict_for_assessment(
                self.identity_score,
                self.checks,
                severe_forbidden_drift=self.severe_forbidden_drift,
            )
        elif self.scoring_version == "terra_python_v2":
            missing = set(LEGACY_GUARDIAN_REQUIRED_CHECKS) - set(self.checks)
            if missing:
                raise ValueError(f"Guardian checks are missing required keys: {sorted(missing)}")
            expected_score = calculate_legacy_guardian_identity_score(self.checks)
            if not isclose(self.identity_score, expected_score, abs_tol=0.01):
                raise ValueError(
                    f"identity_score must be the legacy Python weighted result {expected_score}"
                )
            expected = guardian_verdict_for_score(self.identity_score)
        else:
            expected = guardian_verdict_for_score(self.identity_score)
        if self.verdict != expected:
            raise ValueError(
                f"Guardian score {self.identity_score} requires verdict {expected.value}, "
                f"not {self.verdict.value}"
            )
        if self.verdict != GuardianVerdict.PASS and not self.revision_instruction:
            raise ValueError("Rejected or revisable candidates require revision instructions")
        return self


class GuardianCheck(StrictModel):
    score: float = Field(ge=0, le=100)
    reason: str = Field(min_length=1)


class GuardianCheckSet(StrictModel):
    original_ip_recognition: GuardianCheck
    identity_anchor_consistency: GuardianCheck
    facial_relationship_consistency: GuardianCheck
    structural_grammar_consistency: GuardianCheck
    proportion_signature_consistency: GuardianCheck
    line_style_grammar_consistency: GuardianCheck
    valid_pose_deformation: GuardianCheck
    target_pose_compliance: GuardianCheck
    user_intent_compliance: GuardianCheck
    brand_integration_compliance: GuardianCheck


class GuardianVisionAssessment(StrictModel):
    # Qualitative only and ignored by the authoritative Python gate. Optional
    # for compatibility with Responses fixtures produced before v3.
    verdict: GuardianVerdict | None = None
    checks: GuardianCheckSet
    major_differences: list[str]
    preserve: list[str]
    change_only: list[str]
    candidate_pose: str = ""
    allowed_transformations: list[str] = Field(default_factory=list)
    identity_drift: list[str] = Field(default_factory=list)
    forbidden_drift_detected: bool = False
    severe_forbidden_drift: bool = False
    identity_corrections: list[str] = Field(default_factory=list)
    pose_corrections: list[str] = Field(default_factory=list)
    brand_corrections: list[str] = Field(default_factory=list)
    style_corrections: list[str] = Field(default_factory=list)
    revision_instruction: str | None = None


def calculate_guardian_identity_score(checks: Mapping[str, float]) -> float:
    missing = set(GUARDIAN_IDENTITY_WEIGHTS) - set(checks)
    if missing:
        raise ValueError(f"Guardian identity checks are missing: {sorted(missing)}")
    invalid = {
        key: checks[key]
        for key in GUARDIAN_IDENTITY_WEIGHTS
        if not 0 <= float(checks[key]) <= 100
    }
    if invalid:
        raise ValueError(f"Guardian identity checks must be between 0 and 100: {invalid}")
    return round(
        sum(
            float(checks[key]) * weight
            for key, weight in GUARDIAN_IDENTITY_WEIGHTS.items()
        )
        / 100,
        2,
    )


def calculate_legacy_guardian_identity_score(checks: Mapping[str, float]) -> float:
    missing = set(LEGACY_GUARDIAN_IDENTITY_WEIGHTS) - set(checks)
    if missing:
        raise ValueError(f"Legacy Guardian identity checks are missing: {sorted(missing)}")
    invalid = {
        key: checks[key]
        for key in LEGACY_GUARDIAN_IDENTITY_WEIGHTS
        if not 0 <= float(checks[key]) <= 100
    }
    if invalid:
        raise ValueError(f"Legacy Guardian checks must be between 0 and 100: {invalid}")
    return round(
        sum(
            float(checks[key]) * weight
            for key, weight in LEGACY_GUARDIAN_IDENTITY_WEIGHTS.items()
        )
        / 100,
        2,
    )


def guardian_verdict_for_score(score: float) -> GuardianVerdict:
    if score < 75:
        return GuardianVerdict.REJECT
    if score < 85:
        return GuardianVerdict.REVISE
    return GuardianVerdict.PASS


def guardian_verdict_for_assessment(
    identity_score: float,
    checks: Mapping[str, float],
    *,
    severe_forbidden_drift: bool = False,
) -> GuardianVerdict:
    """Apply the pose-aware identity threshold and three compliance gates."""

    missing = set(GUARDIAN_COMPLIANCE_GATES) - set(checks)
    if missing:
        raise ValueError(f"Guardian compliance gates are missing: {sorted(missing)}")
    invalid = {
        gate: checks[gate]
        for gate in GUARDIAN_COMPLIANCE_GATES
        if not 0 <= float(checks[gate]) <= 100
    }
    if invalid:
        raise ValueError(f"Guardian compliance gates must be between 0 and 100: {invalid}")
    if severe_forbidden_drift or identity_score < 75:
        return GuardianVerdict.REJECT
    if identity_score < 85:
        return GuardianVerdict.REVISE
    if any(float(checks[gate]) < 75 for gate in GUARDIAN_COMPLIANCE_GATES):
        return GuardianVerdict.REVISE
    return GuardianVerdict.PASS


class RankingResult(StrictModel):
    WEIGHTS: ClassVar[dict[str, float]] = RANKING_WEIGHTS

    candidate_id: str
    total_score: float = Field(ge=0, le=100)
    score_breakdown: dict[str, float]
    score_reasons: dict[str, str]
    evidence: list[str] = Field(default_factory=list)
    explanation: str | None = None

    @model_validator(mode="after")
    def validate_weighted_result(self) -> "RankingResult":
        required = set(self.WEIGHTS)
        breakdown_keys = set(self.score_breakdown)
        reason_keys = set(self.score_reasons)
        if breakdown_keys != required:
            raise ValueError(
                f"score_breakdown keys must exactly match ranking dimensions; "
                f"missing={sorted(required - breakdown_keys)}, "
                f"extra={sorted(breakdown_keys - required)}"
            )
        if reason_keys != required:
            raise ValueError(
                f"score_reasons keys must exactly match ranking dimensions; "
                f"missing={sorted(required - reason_keys)}, "
                f"extra={sorted(reason_keys - required)}"
            )
        invalid = {
            key: value for key, value in self.score_breakdown.items() if not 0 <= value <= 100
        }
        if invalid:
            raise ValueError(f"Ranking dimension scores must be between 0 and 100: {invalid}")
        expected = round(
            sum(self.score_breakdown[key] * weight for key, weight in self.WEIGHTS.items()),
            2,
        )
        if not isclose(self.total_score, expected, abs_tol=0.01):
            raise ValueError(f"total_score must be the weighted result {expected}")
        return self

    @classmethod
    def from_scores(
        cls,
        *,
        candidate_id: str,
        score_breakdown: dict[str, float],
        score_reasons: dict[str, str],
        evidence: list[str] | None = None,
        explanation: str | None = None,
    ) -> "RankingResult":
        total = round(
            sum(score_breakdown[key] * weight for key, weight in cls.WEIGHTS.items()),
            2,
        )
        return cls(
            candidate_id=candidate_id,
            total_score=total,
            score_breakdown=score_breakdown,
            score_reasons=score_reasons,
            evidence=list(evidence or []),
            explanation=explanation,
        )


class RankingNarrative(StrictModel):
    score_reasons: dict[str, str]
    evidence: list[str]
    explanation: str


LEGACY_REQUIRED_PACKAGE_FILES: tuple[str, ...] = (
    "result.png",
    "creative_brief.json",
    "ip_identity.json",
    "brand_profile.json",
    "fusion_strategy.json",
    "guardian_report.json",
    "ranking.json",
    "workflow_trace.json",
    "design_guide.md",
    "prompt_trace.json",
)


REQUIRED_PACKAGE_FILES: tuple[str, ...] = (
    "result.png",
    "creative_brief.json",
    "ip_identity_grammar.json",
    "ip_identity.json",
    "brand_profile.json",
    "brand_feature_pool.json",
    "fusion_strategy.json",
    "ip_adaptation.json",
    "guardian_report.json",
    "ranking.json",
    "workflow_trace.json",
    "design_guide.md",
    "prompt_trace.json",
)


class DesignPackage(StrictModel):
    # Historical packages did not contain the schema-v2 grammar, feature-pool,
    # and adaptation artifacts. New workflow agents set this to 2 explicitly.
    package_schema_version: int = Field(default=1, ge=1)
    package_name: str = "following-blowing-design-package.zip"
    result_image_uri: str
    files: list[str] = Field(
        default_factory=lambda: list(LEGACY_REQUIRED_PACKAGE_FILES)
    )
    manifest: dict[str, str] = Field(default_factory=dict)
    copy_description: str = ""
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_package_files(self) -> "DesignPackage":
        required = (
            REQUIRED_PACKAGE_FILES
            if self.package_schema_version >= 2
            else LEGACY_REQUIRED_PACKAGE_FILES
        )
        required_metadata = set(required) - {"result.png"}
        missing = required_metadata - set(self.files)
        if missing:
            raise ValueError(f"Design package is missing required files: {sorted(missing)}")
        if not any(
            name in self.files
            for name in ("result.png", "result.jpg", "result.jpeg", "result.webp")
        ):
            raise ValueError("Design package requires a real result image entry")
        object.__setattr__(self, "files", list(dict.fromkeys(self.files)))
        return self


class AgentExecutionResult(StrictModel):
    status: AgentStatus
    agent_name: str
    input_summary: str
    decision_summary: str
    evidence: list[str] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    output_summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = Field(ge=0)
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    retryable: bool = False
    retry_count: int = Field(default=0, ge=0)
    prompt_id: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    model_route: Literal["fast", "main", "image"] | None = None
    model: str | None = None
    responsibility: str = ""
    handoff: str = ""

    @model_validator(mode="after")
    def validate_execution_timestamps(self) -> "AgentExecutionResult":
        if self.status in {AgentStatus.COMPLETED, AgentStatus.FAILED} and self.completed_at is None:
            raise ValueError("Terminal execution records require completed_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.status == AgentStatus.FAILED and not self.error:
            raise ValueError("Failed execution records require an error message")
        return self


class WorkflowSnapshot(StrictModel):
    checkpoint_version: int = Field(default=1, ge=1)
    workflow_schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=0, ge=0)
    run_id: str
    status: WorkflowStatus
    input_assets: InputAssets
    user_intent: UserIntent
    current_agent: str | None = None
    last_completed_agent: str | None = None
    failed_agent: str | None = None
    pending_agents: list[str] = Field(default_factory=list)
    completed_agents: list[str] = Field(default_factory=list)
    execution_records: list[AgentExecutionResult] = Field(default_factory=list)
    outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    guardian_retries: int = Field(default=0, ge=0)
    max_guardian_retries: int = Field(default=2, ge=0)
    error: str | None = None
    compatibility_warnings: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None

    @field_validator("completed_agents")
    @classmethod
    def completed_agents_are_unique(cls, agents: list[str]) -> list[str]:
        if len(agents) != len(set(agents)):
            raise ValueError("completed_agents must contain unique agent names")
        return agents

    @model_validator(mode="after")
    def validate_workflow_state(self) -> "WorkflowSnapshot":
        if self.guardian_retries > self.max_guardian_retries:
            raise ValueError("guardian_retries cannot exceed max_guardian_retries")
        if self.status == WorkflowStatus.COMPLETED:
            if self.pending_agents:
                raise ValueError("Completed workflows cannot retain pending agents")
            if self.completed_at is None:
                raise ValueError("Completed workflows require completed_at")
            if self.workflow_schema_version >= 2:
                from app.workflow.graph import AGENT_ORDER

                if self.completed_agents != list(AGENT_ORDER):
                    raise ValueError(
                        "Schema-v2 completed workflows require all twelve agents in order"
                    )
                missing_outputs = set(AGENT_ORDER) - set(self.outputs)
                if missing_outputs:
                    raise ValueError(
                        "Schema-v2 completed workflows are missing outputs: "
                        f"{sorted(missing_outputs)}"
                    )
        if (
            self.workflow_schema_version >= 2
            and "IP Guardian Agent" in self.completed_agents
        ):
            try:
                guardian = GuardianResult.model_validate(
                    self.outputs["IP Guardian Agent"]
                )
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    "Schema-v2 Guardian completion requires a valid Guardian output"
                ) from exc
            if guardian.scoring_version != "pose_aware_grammar_v3":
                raise ValueError(
                    "Schema-v2 workflows require the pose-aware Guardian contract"
                )
        if self.status == WorkflowStatus.FAILED and not self.error:
            raise ValueError("Failed workflows require an error message")
        return self
