from __future__ import annotations

from pathlib import Path

from app.config import PROJECT_ROOT, load_settings
from app.controller import ApplicationController
from app.providers.demo_ai import DemoAIProvider
from app.schemas import (
    BrandFeaturePool,
    CollaborationResearch,
    IPIntelligenceResult,
    InputAssets,
    UserIntent,
    WorkflowStatus,
)
from app.services.context_budget import (
    compact_brand_pool,
    compact_collaboration_research,
    compact_ip_for_brief,
)
from app.workflow.engine import WorkflowEngine
from app.workflow.graph import AgentNames


class RecordingDemoAIProvider(DemoAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str | None, str | None]] = []

    def analyze_multimodal(self, **kwargs):
        response_model = kwargs.get("response_model")
        self.calls.append(
            (
                "vision",
                kwargs.get("model_role"),
                getattr(response_model, "__name__", None),
            )
        )
        return super().analyze_multimodal(**kwargs)

    def generate_structured(self, **kwargs):
        response_model = kwargs.get("response_model")
        self.calls.append(
            (
                "structured",
                kwargs.get("model_role"),
                getattr(response_model, "__name__", None),
            )
        )
        return super().generate_structured(**kwargs)

    def generate_text(self, **kwargs):
        self.calls.append(("text", kwargs.get("model_role"), None))
        return super().generate_text(**kwargs)


def test_workflow_agents_route_fast_and_main_models_without_dag_changes() -> None:
    provider = RecordingDemoAIProvider()
    engine = WorkflowEngine(ai_provider=provider)
    engine.start(
        input_assets=InputAssets(ip_image="ip.png", brand_image="brand.png"),
        user_intent=UserIntent(
            selected_goals=["服装融合", "品牌配色"],
            goal_text="保留用户指定的原始表情",
            ai_suggestion={"idea": "增加轻量场景"},
            ai_suggestion_adopted=True,
        ),
        run_id="routing-test",
    )
    snapshot = engine.run_until_complete()

    assert snapshot.status == WorkflowStatus.COMPLETED
    assert [name for kind, role, name in provider.calls if kind == "vision" and role == "main"] == [
        "IPIntelligenceResult",
        "BrandProfile",
        "GuardianVisionAssessment",
    ]
    # DemoAIProvider implements vision by delegating to generate_structured, so
    # the structured interface also records those three schema parses.
    main_structured = [
        name
        for kind, role, name in provider.calls
        if kind == "structured" and role == "main"
    ]
    assert "CreativeBrief" in main_structured
    assert "FusionStrategy" in main_structured
    assert "CollaborationResearchReasoning" in main_structured
    assert "BrandFeaturePool" in main_structured
    assert "IPAdaptationPlan" in main_structured
    assert "RankingNarrative" in main_structured
    assert ("text", "fast", None) in provider.calls

    brief = snapshot.outputs[AgentNames.CREATIVE_BRIEF]
    brand_profile = snapshot.outputs[AgentNames.BRAND_INTELLIGENCE]
    assert brief["priority_stack"] == [
        "保留用户指定的原始表情",
        "服装融合",
        "品牌配色",
        "idea: 增加轻量场景",
    ]
    assert "guardian_metrics" not in snapshot.outputs[AgentNames.FUSION_GENERATION]
    assert brand_profile["logo_features"] == [
        "primary logo geometry visible in the reference"
    ]
    assert "Golden Arches" not in str(brand_profile)

    compact_ip = compact_ip_for_brief(
        IPIntelligenceResult.model_validate(
            snapshot.outputs[AgentNames.IP_INTELLIGENCE]
        )
    )
    compact_brand = compact_brand_pool(
        BrandFeaturePool.model_validate(snapshot.outputs[AgentNames.BRAND_FEATURE])
    )
    compact_research = compact_collaboration_research(
        CollaborationResearch.model_validate(
            snapshot.outputs[AgentNames.BRAND_COLLABORATION]
        )
    )
    assert "pose_transformation_rules" not in compact_ip["identity_grammar"]
    assert "evidence" not in compact_brand["features"][0]
    assert len(compact_research["results"]) <= 6


def test_ai_supplement_routes_to_fast_model_and_keeps_user_input(tmp_path: Path) -> None:
    settings = load_settings(
        project_root=PROJECT_ROOT,
        environ={"DEMO_MODE": "true", "DATA_DIR": str(tmp_path / "data")},
    )
    provider = RecordingDemoAIProvider()
    controller = ApplicationController(settings, ai_provider=provider)

    suggestion = controller.create_ai_suggestion(
        selected_goals=["服装融合"],
        goal_text="用户要求保留原始眼睛位置",
        version=1,
    )

    assert provider.calls[0][0:2] == ("structured", "fast")
    assert "用户要求保留原始眼睛位置" in suggestion["user_input_acknowledgement"]
