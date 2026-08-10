from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agents.base import AgentContext
from app.agents.ip_guardian import IPGuardianAgent
from app.agents.ranking import RankingAgent
from app.config import PROJECT_ROOT, load_settings
from app.controller import ApplicationController
from app.prompt_loader import PROMPT_DIR, load_prompt
from app.providers.demo_ai import DemoAIProvider
from app.schemas import (
    GUARDIAN_IDENTITY_WEIGHTS,
    BrandFeature,
    BrandFeaturePool,
    CreativeBrief,
    DesignPackage,
    FusionDepth,
    FusionStrategy,
    GuardianCheck,
    GuardianCheckSet,
    GuardianResult,
    GuardianVerdict,
    GuardianVisionAssessment,
    IPAdaptationPlan,
    IPIdentityGrammar,
    IPIntelligenceResult,
    InputAssets,
    LEGACY_REQUIRED_PACKAGE_FILES,
    TransformationLevel,
    UserIntent,
    WorkflowSnapshot,
    WorkflowStatus,
    calculate_guardian_identity_score,
    guardian_verdict_for_assessment,
)
from app.workflow.engine import CURRENT_WORKFLOW_SCHEMA_VERSION, WorkflowEngine
from app.workflow.graph import AGENT_ORDER, AgentNames, WorkflowGraph


@pytest.fixture(scope="module")
def organic_snapshot():
    engine = WorkflowEngine()
    engine.start(
        input_assets=InputAssets(ip_image="ip.png", brand_image="brand.png"),
        user_intent=UserIntent(
            selected_goals=["服装融合", "产品元素", "场景融合"],
            goal_text="让角色改成坐姿，挥手并拿着品牌产品",
        ),
        run_id="run_identity_grammar_fixture",
    )
    snapshot = engine.run_until_complete()
    assert snapshot.status == WorkflowStatus.COMPLETED
    return snapshot


def _guardian_values(**overrides: float) -> dict[str, float]:
    values = {
        "original_ip_recognition": 90.0,
        "identity_anchor_consistency": 90.0,
        "facial_relationship_consistency": 90.0,
        "structural_grammar_consistency": 90.0,
        "proportion_signature_consistency": 90.0,
        "line_style_grammar_consistency": 90.0,
        "valid_pose_deformation": 95.0,
        "target_pose_compliance": 90.0,
        "user_intent_compliance": 90.0,
        "brand_integration_compliance": 90.0,
    }
    values.update(overrides)
    return values


def _assessment(
    values: dict[str, float],
    *,
    severe_forbidden_drift: bool = False,
    candidate_pose: str = "sitting and waving",
    identity_drift: list[str] | None = None,
) -> GuardianVisionAssessment:
    return GuardianVisionAssessment(
        verdict=GuardianVerdict.PASS,
        checks=GuardianCheckSet(
            **{
                key: GuardianCheck(score=value, reason=f"evidence for {key}")
                for key, value in values.items()
            }
        ),
        major_differences=["pose changed from standing to sitting"],
        preserve=["facial grammar", "ear grammar"],
        change_only=["pose", "limbs", "viewpoint", "clothing"],
        candidate_pose=candidate_pose,
        allowed_transformations=["pose change", "limb movement", "viewpoint change"],
        identity_drift=list(identity_drift or []),
        forbidden_drift_detected=bool(identity_drift),
        severe_forbidden_drift=severe_forbidden_drift,
        identity_corrections=["restore nose-mouth relationship"] if identity_drift else [],
        pose_corrections=[],
        brand_corrections=[],
        style_corrections=[],
        revision_instruction=(
            "Restore the original nose-mouth relationship."
            if severe_forbidden_drift
            else None
        ),
    )


class _AssessmentProvider:
    def __init__(self, assessment: GuardianVisionAssessment) -> None:
        self.assessment = assessment
        self.call = None

    def analyze_multimodal(self, **kwargs):
        self.call = kwargs
        return self.assessment


def _guardian_result(snapshot, assessment: GuardianVisionAssessment) -> GuardianResult:
    provider = _AssessmentProvider(assessment)
    context = AgentContext(
        run_id=snapshot.run_id,
        input_assets=snapshot.input_assets,
        user_intent=snapshot.user_intent,
        outputs=snapshot.outputs,
    )
    return IPGuardianAgent(ai_provider=provider).process(context).output


def test_workflow_has_exactly_twelve_agents_and_adaptation_edge() -> None:
    assert len(AGENT_ORDER) == 12
    assert AGENT_ORDER.index(AgentNames.FUSION_DECISION) + 1 == AGENT_ORDER.index(
        AgentNames.IP_ADAPTATION
    )
    assert AGENT_ORDER.index(AgentNames.IP_ADAPTATION) + 1 == AGENT_ORDER.index(
        AgentNames.FUSION_GENERATION
    )
    graph = WorkflowGraph()
    assert graph.requirements_for(AgentNames.IP_ADAPTATION) == (
        AgentNames.FUSION_DECISION,
    )
    assert graph.requirements_for(AgentNames.FUSION_GENERATION) == (
        AgentNames.IP_ADAPTATION,
    )


def test_identity_grammar_contains_pose_dependent_and_deformation_rules(
    organic_snapshot,
) -> None:
    result = IPIntelligenceResult.model_validate(
        organic_snapshot.outputs[AgentNames.IP_INTELLIGENCE]
    )
    grammar = result.identity_grammar
    assert isinstance(grammar, IPIdentityGrammar)
    assert grammar.core_identity_anchors
    assert grammar.deformable_features
    assert grammar.pose_dependent_features
    assert grammar.pose_transformation_rules
    assert grammar.viewpoint_transformation_rules
    assert "pose" in grammar.mutable_features


def test_old_identity_lock_checkpoint_projects_to_compatibility_grammar(
    organic_snapshot,
) -> None:
    current = organic_snapshot.outputs[AgentNames.IP_INTELLIGENCE]
    legacy = {
        "ip_dna": current["ip_dna"],
        "identity_lock": current["identity_lock"],
    }
    parsed = IPIntelligenceResult.model_validate(legacy)
    assert parsed.identity_grammar is not None
    assert parsed.identity_lock is not None
    assert "Compatibility projection" in parsed.identity_grammar.unknowns[0]
    assert parsed.identity_grammar.confidence <= 0.5


def test_brand_feature_affordance_contract(organic_snapshot) -> None:
    pool = BrandFeaturePool.model_validate(
        organic_snapshot.outputs[AgentNames.BRAND_FEATURE]
    )
    assert pool.features
    product = next(feature for feature in pool.features if feature.category == "product")
    assert isinstance(product, BrandFeature)
    assert "product_interaction" in product.integration_affordances
    assert "held object" in product.preferred_uses
    assert "replace IP face" in product.avoid_uses
    assert product.attachment_targets
    assert product.occlusion_risk
    assert product.identity_conflict_risk


def test_fusion_decision_persists_relationship_and_organic_depth(organic_snapshot) -> None:
    strategy = FusionStrategy.model_validate(
        organic_snapshot.outputs[AgentNames.FUSION_DECISION]
    )
    assert strategy.fusion_relationship.interaction
    assert strategy.fusion_relationship.behavior
    assert strategy.fusion_relationship.product_interaction
    assert strategy.fusion_relationship.fusion_depth in {
        FusionDepth.PRODUCT_INTERACTION,
        FusionDepth.BEHAVIOR,
        FusionDepth.ROLE,
        FusionDepth.NARRATIVE,
    }


def test_ip_adaptation_plan_schema_and_high_transformation(organic_snapshot) -> None:
    raw = organic_snapshot.outputs[AgentNames.IP_ADAPTATION]
    plan = IPAdaptationPlan.model_validate(raw)
    assert plan.transformation_level == TransformationLevel.HIGH
    assert plan.target_pose != "保持原始姿势"
    assert plan.pose_blueprint.head_orientation
    assert plan.deformation_map.pose_dependent
    assert plan.identity_preservation.anchors_to_preserve
    assert plan.brand_attachment.held_objects
    assert any("Re-pose" in item for item in plan.generation_instructions)
    with pytest.raises(ValidationError):
        IPAdaptationPlan.model_validate(
            {key: value for key, value in raw.items() if key != "pose_blueprint"}
        )


def test_fusion_generation_uses_identity_reference_not_frozen_pose(
    organic_snapshot,
) -> None:
    prompt = organic_snapshot.outputs[AgentNames.FUSION_GENERATION][
        "generation_prompt"
    ]
    lowered = prompt.casefold()
    for forbidden in (
        "preserve exact silhouette",
        "preserve exact pose",
        "preserve exact body outline",
    ):
        assert forbidden not in lowered
    assert "identity reference" in lowered
    assert "not a frozen pose" in lowered
    assert "re-pose the character" in lowered
    assert "ip_adaptation_plan" in lowered


def test_different_pose_can_pass_when_identity_grammar_is_valid(organic_snapshot) -> None:
    result = _guardian_result(organic_snapshot, _assessment(_guardian_values()))
    assert result.candidate_pose == "sitting and waving"
    assert result.identity_score >= 85
    assert result.verdict == GuardianVerdict.PASS


def test_same_pose_can_reject_when_core_face_has_forbidden_drift(
    organic_snapshot,
) -> None:
    assessment = _assessment(
        _guardian_values(),
        severe_forbidden_drift=True,
        candidate_pose="same as original",
        identity_drift=["nose-mouth relationship redesigned"],
    )
    result = _guardian_result(organic_snapshot, assessment)
    assert result.identity_score >= 85
    assert result.severe_forbidden_drift is True
    assert result.verdict == GuardianVerdict.REJECT
    assert result.identity_corrections


def test_nose_mouth_drift_is_penalized_through_facial_relationship_check() -> None:
    baseline = calculate_guardian_identity_score(_guardian_values())
    drifted = calculate_guardian_identity_score(
        _guardian_values(facial_relationship_consistency=0)
    )
    assert baseline - drifted == 13.5
    assert drifted < 85


def test_pose_change_itself_does_not_heavily_penalize_identity() -> None:
    values = _guardian_values(valid_pose_deformation=100, target_pose_compliance=95)
    score = calculate_guardian_identity_score(values)
    assert score >= 90
    assert guardian_verdict_for_assessment(score, values) == GuardianVerdict.PASS


def test_pose_aware_guardian_python_weights_are_exact() -> None:
    assert GUARDIAN_IDENTITY_WEIGHTS == {
        "original_ip_recognition": 25,
        "identity_anchor_consistency": 20,
        "facial_relationship_consistency": 15,
        "structural_grammar_consistency": 15,
        "proportion_signature_consistency": 10,
        "line_style_grammar_consistency": 10,
        "valid_pose_deformation": 5,
    }
    assert sum(GUARDIAN_IDENTITY_WEIGHTS.values()) == 100
    values = _guardian_values(
        original_ip_recognition=100,
        identity_anchor_consistency=80,
        facial_relationship_consistency=60,
        structural_grammar_consistency=40,
        proportion_signature_consistency=20,
        line_style_grammar_consistency=0,
        valid_pose_deformation=100,
    )
    assert calculate_guardian_identity_score(values) == 63.0


@pytest.mark.parametrize(
    "gate",
    [
        "target_pose_compliance",
        "user_intent_compliance",
        "brand_integration_compliance",
    ],
)
def test_each_compliance_gate_can_force_revise(gate: str) -> None:
    values = _guardian_values(**{gate: 74})
    score = calculate_guardian_identity_score(values)
    assert score >= 85
    assert guardian_verdict_for_assessment(score, values) == GuardianVerdict.REVISE


def test_guardian_revision_separates_identity_pose_brand_and_style(
    organic_snapshot,
) -> None:
    values = _guardian_values(
        facial_relationship_consistency=50,
        target_pose_compliance=60,
        brand_integration_compliance=60,
    )
    assessment = _assessment(values, identity_drift=["nose-mouth drift"])
    assessment = assessment.model_copy(
        update={
            "pose_corrections": ["raise the right limb into a clear wave"],
            "brand_corrections": ["move logo onto the uniform chest panel"],
            "style_corrections": ["restore minimal contour line"],
        }
    )
    result = _guardian_result(organic_snapshot, assessment)
    assert result.verdict != GuardianVerdict.PASS
    assert result.identity_corrections
    assert result.pose_corrections
    assert result.brand_corrections
    assert result.style_corrections
    assert result.revision_instruction


def test_ranking_penalizes_sticker_only_and_reuses_guardian_score(
    organic_snapshot,
) -> None:
    outputs = dict(organic_snapshot.outputs)
    organic_strategy = FusionStrategy.model_validate(outputs[AgentNames.FUSION_DECISION])

    def rank(depth: FusionDepth):
        relationship = organic_strategy.fusion_relationship.model_copy(
            update={"fusion_depth": depth}
        )
        strategy = organic_strategy.model_copy(
            update={"fusion_relationship": relationship}
        )
        changed = dict(outputs)
        changed[AgentNames.FUSION_DECISION] = strategy.model_dump(mode="json")
        context = AgentContext(
            run_id=organic_snapshot.run_id,
            input_assets=organic_snapshot.input_assets,
            user_intent=organic_snapshot.user_intent,
            outputs=changed,
        )
        return RankingAgent(ai_provider=DemoAIProvider()).process(context).output

    sticker = rank(FusionDepth.STICKER)
    role = rank(FusionDepth.ROLE)
    guardian = GuardianResult.model_validate(
        organic_snapshot.outputs[AgentNames.IP_GUARDIAN]
    )
    assert sticker.score_breakdown["fusion_naturalness"] < role.score_breakdown[
        "fusion_naturalness"
    ]
    assert sticker.score_breakdown["innovation"] < role.score_breakdown["innovation"]
    assert role.score_breakdown["ip_identity_consistency"] == guardian.identity_score


def test_design_package_contract_contains_identity_grammar_and_adaptation(
    organic_snapshot,
) -> None:
    package = DesignPackage.model_validate(
        organic_snapshot.outputs[AgentNames.DESIGN_PACKAGE]
    )
    assert "ip_identity_grammar.json" in package.files
    assert "brand_feature_pool.json" in package.files
    assert "ip_adaptation.json" in package.files
    assert package.manifest["ip_identity_grammar.json"] == AgentNames.IP_INTELLIGENCE
    assert package.manifest["ip_adaptation.json"] == AgentNames.IP_ADAPTATION


def test_all_three_dependency_invalidations_include_ip_adaptation() -> None:
    graph = WorkflowGraph()
    for root in (
        AgentNames.CREATIVE_BRIEF,
        AgentNames.IP_PREPARATION,
        AgentNames.BRAND_INTELLIGENCE,
    ):
        assert AgentNames.IP_ADAPTATION in graph.descendants_of(root)


def test_demo_mode_runs_and_persists_all_twelve_agents(organic_snapshot) -> None:
    assert organic_snapshot.workflow_schema_version == CURRENT_WORKFLOW_SCHEMA_VERSION
    assert organic_snapshot.completed_agents == list(AGENT_ORDER)
    assert set(organic_snapshot.outputs) == set(AGENT_ORDER)
    assert len(organic_snapshot.execution_records) == 12


def _legacy_checkpoint(snapshot) -> dict:
    legacy = snapshot.model_dump(mode="json")
    legacy.pop("workflow_schema_version", None)
    legacy.pop("compatibility_warnings", None)
    legacy["completed_agents"].remove(AgentNames.IP_ADAPTATION)
    legacy["outputs"].pop(AgentNames.IP_ADAPTATION, None)
    legacy["execution_records"] = [
        record
        for record in legacy["execution_records"]
        if record["agent_name"] != AgentNames.IP_ADAPTATION
    ]
    legacy["outputs"][AgentNames.IP_INTELLIGENCE].pop("identity_grammar", None)
    legacy["outputs"][AgentNames.BRAND_FEATURE].pop("features", None)
    legacy["outputs"][AgentNames.BRAND_FEATURE].pop("organic_fusion_guidance", None)
    return legacy


def test_legacy_completed_checkpoint_migrates_without_fabricating_adaptation(
    organic_snapshot,
) -> None:
    restored = WorkflowEngine.from_checkpoint(_legacy_checkpoint(organic_snapshot)).snapshot
    assert restored is not None
    assert restored.workflow_schema_version == 2
    assert restored.status == WorkflowStatus.RUNNING
    assert AgentNames.IP_ADAPTATION not in restored.outputs
    assert AgentNames.IP_INTELLIGENCE in restored.pending_agents
    assert "legacy_workflow_schema_v1_migrated_for_execution" in restored.compatibility_warnings


def test_controller_legacy_audit_restore_does_not_crash_or_mutate_disk(
    tmp_path: Path,
) -> None:
    settings = load_settings(
        project_root=PROJECT_ROOT,
        environ={"DATA_DIR": str(tmp_path / "data"), "DEMO_MODE": "true"},
    )
    controller = ApplicationController(settings)
    assets = controller.bootstrap_demo_assets()
    snapshot = controller.start_workflow(
        ip_asset_id=assets["ip"].asset_id,
        brand_asset_id=assets["brand"].asset_id,
        selected_goals=["产品元素"],
        goal_text="坐着挥手",
        ai_suggestion=None,
        ai_suggestion_adopted=False,
    )
    while snapshot.status != WorkflowStatus.COMPLETED:
        snapshot = controller.advance_workflow(snapshot.run_id)
    legacy = _legacy_checkpoint(snapshot)
    controller.repository.save_checkpoint(snapshot.run_id, legacy)

    audited = controller.restore_snapshot(snapshot.run_id)
    persisted = controller.repository.get_checkpoint(snapshot.run_id)
    assert audited.status == WorkflowStatus.COMPLETED
    assert audited.workflow_schema_version == 1
    assert "legacy_workflow_schema_v1_audit_restore" in audited.compatibility_warnings
    assert "workflow_schema_version" not in persisted
    assert AgentNames.IP_ADAPTATION not in persisted["outputs"]


def test_schema_v2_checkpoint_rejects_legacy_guardian_contract(
    organic_snapshot,
) -> None:
    raw = organic_snapshot.model_dump(mode="json")
    candidate_id = raw["outputs"][AgentNames.FUSION_GENERATION]["candidate_id"]
    raw["outputs"][AgentNames.IP_GUARDIAN] = GuardianResult(
        candidate_id=candidate_id,
        identity_score=90,
        score=90,
        verdict=GuardianVerdict.PASS,
        checks={
            "original_ip_recognition": 90,
            "silhouette": 90,
            "head_body_structure": 90,
            "ear_structure": 90,
            "eye_structure": 90,
            "nose_mouth": 90,
            "body_proportions": 90,
            "line_language": 90,
            "user_intent_constraints": 90,
        },
        intent_constraints_met=True,
        scoring_version="terra_python_v2",
    ).model_dump(mode="json")

    with pytest.raises(ValidationError, match="pose-aware Guardian contract"):
        WorkflowSnapshot.model_validate(raw)


def test_controller_retry_migrates_legacy_failed_checkpoint_before_retry(
    tmp_path: Path,
) -> None:
    settings = load_settings(
        project_root=PROJECT_ROOT,
        environ={"DATA_DIR": str(tmp_path / "data"), "DEMO_MODE": "true"},
    )
    controller = ApplicationController(settings)
    assets = controller.bootstrap_demo_assets()
    snapshot = controller.start_workflow(
        ip_asset_id=assets["ip"].asset_id,
        brand_asset_id=assets["brand"].asset_id,
        selected_goals=["产品元素"],
        goal_text="坐着挥手",
        ai_suggestion=None,
        ai_suggestion_adopted=False,
    )
    legacy_failed = snapshot.model_dump(mode="json")
    legacy_failed.pop("workflow_schema_version", None)
    legacy_failed.pop("compatibility_warnings", None)
    legacy_failed.update(
        status="failed",
        failed_agent=AgentNames.IP_PREPARATION,
        current_agent=AgentNames.IP_PREPARATION,
        error="legacy preparation failure",
    )
    controller.repository.save_checkpoint(snapshot.run_id, legacy_failed)

    migrated = controller.retry_current_agent(snapshot.run_id)
    persisted = controller.repository.get_checkpoint(snapshot.run_id)
    run = controller.repository.get_run(snapshot.run_id)
    assert migrated.workflow_schema_version == CURRENT_WORKFLOW_SCHEMA_VERSION
    assert migrated.status == WorkflowStatus.RUNNING
    assert migrated.failed_agent is None
    assert migrated.pending_agents[0] == AgentNames.IP_PREPARATION
    assert persisted["workflow_schema_version"] == CURRENT_WORKFLOW_SCHEMA_VERSION
    assert run["workflow_schema_version"] == CURRENT_WORKFLOW_SCHEMA_VERSION


def test_controller_can_export_audited_schema_v1_package(tmp_path: Path) -> None:
    settings = load_settings(
        project_root=PROJECT_ROOT,
        environ={"DATA_DIR": str(tmp_path / "data"), "DEMO_MODE": "true"},
    )
    controller = ApplicationController(settings)
    assets = controller.bootstrap_demo_assets()
    snapshot = controller.start_workflow(
        ip_asset_id=assets["ip"].asset_id,
        brand_asset_id=assets["brand"].asset_id,
        selected_goals=["产品元素"],
        goal_text="历史联名目标",
        ai_suggestion=None,
        ai_suggestion_adopted=False,
    )
    while snapshot.status != WorkflowStatus.COMPLETED:
        snapshot = controller.advance_workflow(snapshot.run_id)

    legacy = _legacy_checkpoint(snapshot)
    package = legacy["outputs"][AgentNames.DESIGN_PACKAGE]
    package.pop("package_schema_version", None)
    package["files"] = list(LEGACY_REQUIRED_PACKAGE_FILES)
    package["manifest"] = {
        name: value
        for name, value in package["manifest"].items()
        if name in LEGACY_REQUIRED_PACKAGE_FILES
    }
    controller.repository.save_checkpoint(snapshot.run_id, legacy)

    archive_path = controller.export_design_package(snapshot.run_id)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert set(LEGACY_REQUIRED_PACKAGE_FILES) <= names
    assert "ip_identity_grammar.json" not in names
    assert "ip_adaptation.json" not in names


def test_prompt_trace_records_id_version_hash_route_and_model(organic_snapshot) -> None:
    traced = [record for record in organic_snapshot.execution_records if record.prompt_id]
    assert len(traced) == 11
    for record in traced:
        assert record.prompt_version == "3.0.0"
        assert record.prompt_hash and re.fullmatch(r"[0-9a-f]{64}", record.prompt_hash)
        assert record.model_route in {"fast", "main", "image"}
        assert record.model
        assert load_prompt(record.prompt_id).prompt_hash == record.prompt_hash


def test_agent_model_routes_match_fixed_contract(organic_snapshot) -> None:
    routes = {
        record.agent_name: (record.model_route, record.model)
        for record in organic_snapshot.execution_records
        if record.prompt_id
    }
    assert routes[AgentNames.DESIGN_PACKAGE] == ("fast", "gpt-5.6-luna")
    assert routes[AgentNames.FUSION_GENERATION] == ("image", "gpt-image-2")
    for name in (
        AgentNames.IP_INTELLIGENCE,
        AgentNames.BRAND_INTELLIGENCE,
        AgentNames.BRAND_COLLABORATION,
        AgentNames.BRAND_FEATURE,
        AgentNames.CREATIVE_BRIEF,
        AgentNames.FUSION_DECISION,
        AgentNames.IP_ADAPTATION,
        AgentNames.IP_GUARDIAN,
        AgentNames.RANKING,
    ):
        assert routes[name] == ("main", "gpt-5.6-terra")


def test_versioned_prompts_do_not_expose_secrets_or_machine_paths() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PROMPT_DIR.glob("*.md"))
    )
    lowered = combined.casefold()
    assert "api key" not in lowered
    assert "base url" not in lowered
    assert "authorization:" not in lowered
    assert "sk-" not in lowered
    assert "/users/" not in lowered
    assert str(PROJECT_ROOT).casefold() not in lowered


def test_all_prompt_front_matter_matches_file_and_declared_route() -> None:
    for path in sorted(PROMPT_DIR.glob("*.md")):
        spec = load_prompt(path.stem)
        assert spec.prompt_id == path.stem
        assert spec.version == "3.0.0"
        assert spec.model_route in {"fast", "main", "image"}
        assert spec.output_schema
        assert spec.body
