"""Opt-in real Luna/Terra smoke test. Never prints credentials or provider URLs."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.base import AgentContext  # noqa: E402
from app.agents.brand_intelligence import BrandIntelligenceAgent  # noqa: E402
from app.agents.ip_guardian import IPGuardianAgent  # noqa: E402
from app.agents.ip_intelligence import IPIntelligenceAgent  # noqa: E402
from app.agents.ip_preparation import IPPreparationAgent  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.controller import AISuggestion  # noqa: E402
from app.providers import DemoAIProvider, create_ai_provider  # noqa: E402
from app.schemas import CandidateDesign, GuardianVerdict, InputAssets, UserIntent  # noqa: E402
from app.workflow.engine import WorkflowEngine  # noqa: E402
from app.workflow.graph import AgentNames  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.is_file():
        raise SystemExit("Real smoke skipped: .streamlit/secrets.toml is missing")
    secrets = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    settings = load_settings(project_root=PROJECT_ROOT, environ={}, secrets=secrets)
    provider = create_ai_provider(settings)
    if settings.demo_mode or isinstance(provider, DemoAIProvider):
        raise SystemExit("Real smoke refused to run in demo mode")
    expected_routes = {
        "fast": "gpt-5.6-luna",
        "main": "gpt-5.6-terra",
        "image": "gpt-image-2",
    }
    actual_routes = {
        "fast": settings.model_fast,
        "main": settings.model_main,
        "image": settings.image_model,
    }
    if actual_routes != expected_routes:
        raise AssertionError(f"Unexpected model routes: {actual_routes}")

    assets = InputAssets(
        ip_image=str(PROJECT_ROOT / "assets" / "demo" / "ip_reference.jpg"),
        brand_image=str(PROJECT_ROOT / "assets" / "demo" / "brand_reference.jpg"),
        ip_filename="ip_reference.jpg",
        brand_filename="brand_reference.jpg",
        brand_name="Brand shown in reference",
    )
    intent = UserIntent(
        selected_goals=["服装融合", "品牌配色"],
        goal_text="保留原始IP的极简线条、扁平轮廓与原始五官位置关系",
    )
    base_context = AgentContext(
        run_id="real-agent-smoke",
        input_assets=assets,
        user_intent=intent,
        outputs={},
    )
    prepared = IPPreparationAgent().process(base_context).output
    ip_context = AgentContext(
        run_id=base_context.run_id,
        input_assets=assets,
        user_intent=intent,
        outputs={AgentNames.IP_PREPARATION: prepared.model_dump(mode="json")},
    )
    ip_result = IPIntelligenceAgent(ai_provider=provider).process(ip_context).output
    brand_result = BrandIntelligenceAgent(ai_provider=provider).process(base_context).output

    # Build the new pose-aware Guardian dependencies with the deterministic
    # Demo provider. This stops before Fusion Generation, so the smoke never
    # calls GPT Image 2 and only the explicitly tested vision calls are live.
    demo_engine = WorkflowEngine()
    demo_engine.start(
        input_assets=assets,
        user_intent=intent,
        run_id="real-agent-smoke-dependencies",
    )
    demo_snapshot = demo_engine.snapshot
    for _ in range(8):
        demo_snapshot = demo_engine.run_next_step()
    assert demo_snapshot is not None

    candidate = CandidateDesign(
        candidate_id="guardian-rejected-smoke",
        image_uri=str(PROJECT_ROOT / "assets" / "demo" / "guardian_rejected.jpg"),
        theme_name="Guardian rejected fixture",
        fusion_logic="Negative-control candidate for identity comparison",
        design_tags=["negative control"],
        generation_prompt="negative-control fixture",
    )
    guardian_context = AgentContext(
        run_id=base_context.run_id,
        input_assets=assets,
        user_intent=intent,
        outputs={
            AgentNames.IP_INTELLIGENCE: ip_result.model_dump(mode="json"),
            AgentNames.CREATIVE_BRIEF: demo_snapshot.outputs[
                AgentNames.CREATIVE_BRIEF
            ],
            AgentNames.FUSION_DECISION: demo_snapshot.outputs[
                AgentNames.FUSION_DECISION
            ],
            AgentNames.IP_ADAPTATION: demo_snapshot.outputs[
                AgentNames.IP_ADAPTATION
            ],
            AgentNames.FUSION_GENERATION: candidate.model_dump(mode="json"),
        },
    )
    guardian = IPGuardianAgent(ai_provider=provider).process(guardian_context).output

    supplement = provider.generate_structured(
        prompt=(
            "生成结构化联名补充建议。用户自由输入优先；只允许补充，不得覆盖用户输入。"
        ),
        response_model=AISuggestion,
        context={
            "version": 1,
            "selected_goals": intent.selected_goals,
            "user_free_text": intent.goal_text,
        },
        model_role="fast",
    )

    if guardian.verdict not in {GuardianVerdict.REJECT, GuardianVerdict.REVISE}:
        raise AssertionError(
            f"guardian_rejected.jpg unexpectedly received {guardian.verdict.value}"
        )
    required_ip_fields = {
        "character_type",
        "full_body_structure",
        "silhouette",
        "head_structure",
        "head_body_relationship",
        "ear_structure",
        "eye_structure",
        "nose_mouth",
        "limb_structure",
        "body_proportions",
        "pose",
        "line_language",
        "immutable_features",
        "mutable_features",
        "identity_risks",
    }
    ip_dna_values = ip_result.ip_dna.model_dump()
    if not required_ip_fields.issubset(ip_dna_values):
        raise AssertionError("Terra IPDNA omitted required fields")
    empty_ip_fields = [name for name in required_ip_fields if not ip_dna_values[name]]
    if empty_ip_fields:
        raise AssertionError(f"Terra IPDNA returned empty required fields: {empty_ip_fields}")
    grammar = ip_result.identity_grammar
    if grammar is None or not all(
        (
            grammar.core_identity_anchors,
            grammar.relational_geometry,
            grammar.proportion_signature,
            grammar.facial_grammar,
            grammar.line_style_grammar,
            grammar.pose_transformation_rules,
            grammar.forbidden_drift,
        )
    ):
        raise AssertionError("Terra IP Identity Grammar is not complete")
    if not all(
        (
            brand_result.brand_summary.strip(),
            brand_result.logo_features,
            brand_result.color_palette,
            brand_result.visual_language,
            brand_result.evidence,
        )
    ):
        raise AssertionError("Terra BrandProfile is not grounded or complete")
    acknowledgement = supplement.user_input_acknowledgement
    if not all(marker in acknowledgement for marker in ("极简线条", "扁平轮廓", "五官位置关系")):
        raise AssertionError("Luna supplement did not acknowledge the user-owned input")

    print(
        json.dumps(
            {
                "routes": actual_routes,
                "luna_supplement": supplement.model_dump(mode="json"),
                "terra_ip_intelligence": ip_result.model_dump(mode="json"),
                "terra_brand_intelligence": brand_result.model_dump(mode="json"),
                "terra_guardian_python_result": guardian.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
