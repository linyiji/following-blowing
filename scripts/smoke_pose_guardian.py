"""Opt-in, one-call Terra dual-image smoke for the Pose-Aware Guardian.

Supply an independently prepared, different-pose candidate with ``--candidate``.
The script compares it with the packaged original IP and verifies that pose
change alone does not produce an automatic REJECT.  It never invokes GPT Image
2 and never prints credentials, provider URLs, or local absolute paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.base import AgentContext  # noqa: E402
from app.agents.ip_guardian import IPGuardianAgent  # noqa: E402
from app.schemas import (  # noqa: E402
    GUARDIAN_REQUIRED_CHECKS,
    CandidateDesign,
    GuardianResult,
    GuardianVerdict,
)
from app.workflow.graph import AgentNames  # noqa: E402
from scripts.smoke_ip_adaptation import (  # noqa: E402
    IP_REFERENCE,
    adaptation_fixture,
    brief_fixture,
    identity_fixture,
    load_real_terra,
    smoke_assets,
    smoke_intent,
    strategy_fixture,
)


MAX_CANDIDATE_BYTES = 25 * 1024 * 1024


def _usable_candidate(value: Path | None) -> Path | None:
    if value is None:
        print("SKIP: provide a different-pose candidate with --candidate")
        return None
    try:
        candidate = value.expanduser().resolve()
        if not candidate.is_file() or candidate.stat().st_size <= 0:
            print("SKIP: candidate image is missing or empty")
            return None
        if candidate.stat().st_size > MAX_CANDIDATE_BYTES:
            print("SKIP: candidate image exceeds the smoke-test size limit")
            return None
        with Image.open(candidate) as image:
            image.verify()
        if hashlib.sha256(candidate.read_bytes()).digest() == hashlib.sha256(
            IP_REFERENCE.read_bytes()
        ).digest():
            print("SKIP: candidate must differ from the packaged original IP")
            return None
    except (OSError, UnidentifiedImageError, ValueError):
        print("SKIP: candidate is not a readable local image")
        return None
    return candidate


def _guardian_context(candidate_path: Path) -> AgentContext:
    intelligence = identity_fixture()
    adaptation = adaptation_fixture(intelligence)
    brief = brief_fixture()
    strategy = strategy_fixture()
    candidate_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()[:16]
    candidate = CandidateDesign(
        candidate_id=f"pose-smoke-{candidate_hash}",
        image_uri=str(candidate_path),
        theme_name=strategy.theme_name,
        fusion_logic=strategy.fusion_logic,
        design_tags=list(strategy.design_tags),
        generation_prompt=(
            "User-supplied pose-aware Guardian candidate; this smoke performed no image generation."
        ),
        revision_number=0,
        metadata={"source": "user-supplied-pose-smoke-candidate"},
    )
    outputs: dict[str, dict[str, Any]] = {
        AgentNames.IP_INTELLIGENCE: intelligence.model_dump(mode="json"),
        AgentNames.CREATIVE_BRIEF: brief.model_dump(mode="json"),
        AgentNames.FUSION_DECISION: strategy.model_dump(mode="json"),
        AgentNames.IP_ADAPTATION: adaptation.model_dump(mode="json"),
        AgentNames.FUSION_GENERATION: candidate.model_dump(mode="json"),
    }
    return AgentContext(
        run_id="pose-guardian-smoke",
        input_assets=smoke_assets(),
        user_intent=smoke_intent(),
        outputs=outputs,
    )


def _validate_guardian(result: GuardianResult) -> None:
    if result.scoring_version != "pose_aware_grammar_v3":
        raise AssertionError("Guardian did not use the pose-aware scoring contract")
    missing = set(GUARDIAN_REQUIRED_CHECKS) - set(result.checks)
    if missing:
        raise AssertionError("Guardian omitted required pose-aware checks")
    if not result.candidate_pose.strip():
        raise AssertionError("Terra did not describe the candidate pose")
    if not result.check_reasons.get("valid_pose_deformation", "").strip():
        raise AssertionError("Terra did not explain valid pose deformation")
    allowed = " ".join(result.allowed_transformations).casefold()
    if not any(marker in allowed for marker in ("pose", "posture", "姿势")):
        raise AssertionError("Terra did not recognize pose change as an allowed transformation")
    if result.verdict == GuardianVerdict.REJECT:
        raise AssertionError(
            "Pose-aware smoke candidate was rejected; verify identity similarity rather than pose alone"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        type=Path,
        help="local different-pose candidate image prepared outside this smoke",
    )
    args = parser.parse_args(argv)

    candidate = _usable_candidate(args.candidate)
    if candidate is None:
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
    try:
        result = IPGuardianAgent(ai_provider=provider).process(
            _guardian_context(candidate)
        ).output
        _validate_guardian(result)
        records = getattr(provider.provider_client, "records", ())
        logical_calls = len(records) - before
        if logical_calls != 1:
            raise AssertionError("Pose Guardian smoke must make exactly one logical Terra call")
        if not records or records[-1].operation != "ai.analyze_multimodal_structured":
            raise AssertionError("Pose Guardian smoke did not use Terra dual-image analysis")
    except Exception as exc:
        print(f"FAIL: Terra Pose-Aware Guardian smoke ({type(exc).__name__})")
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "model": settings.model_main,
                "logical_terra_calls": 1,
                "gpt_image_2_calls": 0,
                "assertion": "pose change did not automatically produce REJECT",
                "guardian_result": result.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
