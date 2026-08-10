from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
import pytest

from app.config import PROJECT_ROOT, load_settings
from app.controller import ApplicationController
from app.health import AppBootstrap
from app.schemas import InputAssets, UserIntent, WorkflowStatus
from app.services.errors import ImageGenerationError
from app.workflow.engine import WorkflowEngine
from app.workflow.graph import AgentNames


def _start_controller(controller: ApplicationController):
    assets = controller.bootstrap_demo_assets()
    return controller.start_workflow(
        ip_asset_id=assets["ip"].asset_id,
        brand_asset_id=assets["brand"].asset_id,
        selected_goals=["帽子 / 头饰", "品牌配色"],
        goal_text="只增加一顶小红帽，保持原始五官与线条",
        ai_suggestion=None,
        ai_suggestion_adopted=False,
    )


def test_competition_start_is_fresh_and_keeps_old_run_restorable(
    tmp_path: Path,
) -> None:
    settings = load_settings(
        project_root=PROJECT_ROOT,
        environ={
            "DATA_DIR": str(tmp_path / "data"),
            "DEMO_MODE": "true",
            "COMPETITION_MODE": "true",
        },
    )
    controller = ApplicationController(settings)
    first = _start_controller(controller)
    controller.repository.update_run(
        first.run_id,
        final_candidate_id="old-final",
        ranking_result={"total_score": 99},
        design_package_id="old.zip",
    )

    second = _start_controller(controller)
    second_run = controller.repository.get_run(second.run_id)

    assert second.run_id != first.run_id
    assert second.outputs == {}
    assert second.completed_agents == []
    assert second.execution_records == []
    assert second_run["final_candidate_id"] is None
    assert second_run["ranking_result"] is None
    assert second_run["design_package_id"] is None
    assert second_run["competition_mode"] is True
    assert second_run["search_mode"] == "demo"
    assert controller.restore_snapshot(first.run_id).run_id == first.run_id


def test_live_started_at_is_runtime_time_not_build_metadata(tmp_path: Path) -> None:
    settings = load_settings(
        project_root=PROJECT_ROOT,
        environ={
            "DATA_DIR": str(tmp_path / "data"),
            "DEMO_MODE": "true",
            "COMPETITION_MODE": "true",
        },
    )
    controller = ApplicationController(settings)
    before = datetime.now(timezone.utc)
    snapshot = _start_controller(controller)
    after = datetime.now(timezone.utc)
    run = controller.repository.get_run(snapshot.run_id)
    build = json.loads((PROJECT_ROOT / "BUILD_INFO.json").read_text(encoding="utf-8"))

    assert before <= snapshot.started_at <= after
    assert datetime.fromisoformat(run["started_at"]) == snapshot.started_at
    assert run["started_at"] != build["build_started_at"]
    public = controller.public_snapshot(snapshot)
    assert public is not None
    assert public["started_at"] == snapshot.started_at.isoformat()
    assert public["provider_mode"] == "demo"
    assert public["search_mode"] == "demo"


def test_agent_completion_is_not_published_when_checkpoint_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = load_settings(
        project_root=PROJECT_ROOT,
        environ={"DATA_DIR": str(tmp_path / "data"), "DEMO_MODE": "true"},
    )
    controller = ApplicationController(settings)
    snapshot = _start_controller(controller)
    prior_checkpoint = controller.restore_snapshot(snapshot.run_id)

    def fail_checkpoint(*args, **kwargs):
        del args, kwargs
        raise OSError("checkpoint unavailable")

    monkeypatch.setattr(controller.repository, "save_checkpoint", fail_checkpoint)
    with pytest.raises(OSError, match="checkpoint unavailable"):
        controller.advance_workflow(snapshot.run_id)

    run = controller.repository.get_run(snapshot.run_id)
    assert run["agent_results"] == {}
    assert prior_checkpoint.completed_agents == []


def test_search_modes_and_multi_reference_defaults_are_explicit(tmp_path: Path) -> None:
    common = {
        "DATA_DIR": str(tmp_path / "data"),
        "DEMO_MODE": "false",
        "MULTIMODAL_PROVIDER": "openai",
        "MULTIMODAL_API_KEY": "test-multimodal-key",
        "MODEL_MAIN": "gpt-5.6-terra",
        "MODEL_FAST": "gpt-5.6-luna",
        "IMAGE_PROVIDER": "openai",
        "IMAGE_API_KEY": "test-image-key",
        "IMAGE_MODEL": "gpt-image-2",
    }
    demo_search = load_settings(
        project_root=PROJECT_ROOT,
        environ={**common, "SEARCH_PROVIDER": "demo"},
    )
    unverified_search = load_settings(
        project_root=PROJECT_ROOT,
        environ={
            **common,
            "SEARCH_PROVIDER": "openai",
            "SEARCH_API_KEY": "test-search-key",
            "SEARCH_MODEL": "search-model",
        },
    )
    live_search = load_settings(
        project_root=PROJECT_ROOT,
        environ={
            **common,
            "SEARCH_PROVIDER": "openai",
            "SEARCH_API_KEY": "test-search-key",
            "SEARCH_MODEL": "search-model",
            "SEARCH_PROVIDER_VERIFIED": "true",
        },
    )

    assert demo_search.provider_mode == "live"
    assert demo_search.search_mode == "demo"
    assert unverified_search.search_mode == "unverified"
    assert live_search.search_mode == "live"
    assert demo_search.allow_multi_reference_image_edit is False
    assert demo_search.multi_reference_image_edit_status == "UNVERIFIED"
    assert "test-image-key" not in repr(demo_search.public_status())


def _write_verified_image_record(root: Path) -> None:
    smoke = root / "data" / "smoke"
    smoke.mkdir(parents=True)
    artifacts: list[tuple[str, str]] = []
    for name, operation in (
        ("gpt-image-2-single-edit.png", "edit"),
        ("gpt-image-2-generation.png", "generation"),
    ):
        image_path = smoke / name
        Image.new("RGB", (4, 3), (220, 20, 40)).save(image_path, format="PNG")
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        artifacts.append((name, digest))
        marker_name = name.replace(".png", ".json")
        (smoke / marker_name).write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "operation": operation,
                    "model": "gpt-image-2",
                    "artifact": {
                        "local_path": f"data/smoke/{name}",
                        "sha256": digest,
                    },
                }
            ),
            encoding="utf-8",
        )
    (smoke / "image-provider-verification.json").write_text(
        json.dumps(
            {
                "IMAGE_PROVIDER_VERIFIED": True,
                "model": "gpt-image-2",
                "models_endpoint_verified": True,
            }
        ),
        encoding="utf-8",
    )


def test_image_health_requires_hash_validated_dual_smoke_marker(
    tmp_path: Path,
) -> None:
    environment = {
        "DATA_DIR": str(tmp_path / "data"),
        "DEMO_MODE": "false",
        "MULTIMODAL_PROVIDER": "openai",
        "MULTIMODAL_API_KEY": "test-key",
        "IMAGE_PROVIDER": "openai",
        "IMAGE_API_KEY": "test-key",
        "SEARCH_PROVIDER": "demo",
        "IMAGE_PROVIDER_VERIFIED": "true",
    }
    unverified = load_settings(project_root=PROJECT_ROOT, environ=environment)
    assert unverified.image_provider_verified is False
    assert AppBootstrap(unverified).check().image_provider_ready is False

    _write_verified_image_record(tmp_path)
    verified = load_settings(project_root=PROJECT_ROOT, environ=environment)
    health = AppBootstrap(verified).check()
    assert verified.image_provider_verified is True
    assert verified.model_catalog_verified is True
    assert health.image_provider_ready is True
    assert health.luna_ready is True
    assert health.terra_ready is True
    assert health.search_mode == "demo"
    assert "search_provider_demo_mock_research" in health.warnings

    image = tmp_path / "data" / "smoke" / "gpt-image-2-generation.png"
    image.write_bytes(image.read_bytes() + b"tampered")
    tampered = load_settings(project_root=PROJECT_ROOT, environ=environment)
    assert tampered.image_provider_verified is False


class _FirstImageThenFailure:
    multi_reference_image_edit = False
    multi_reference_image_edit_status = "UNVERIFIED"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def edit_with_reference(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return PROJECT_ROOT / "assets" / "demo" / "final_result.png"
        raise ImageGenerationError(
            "Image API request failed",
            request_id="request-test",
            retryable=True,
        )


def test_revision_image_failure_is_retryable_and_preserves_prior_candidate() -> None:
    provider = _FirstImageThenFailure()
    engine = WorkflowEngine(image_provider=provider)
    snapshot = engine.start(
        run_id="run_competition_failure",
        input_assets=InputAssets(
            ip_image=str(PROJECT_ROOT / "assets" / "demo" / "ip_reference.jpg"),
            brand_image=str(PROJECT_ROOT / "assets" / "demo" / "brand_reference.jpg"),
        ),
        user_intent=UserIntent(
            selected_goals=["帽子 / 头饰"],
            goal_text="保持原始结构，只添加小红帽",
            metadata={"guardian_score_sequence": [70, 90]},
        ),
    )
    for _ in range(10):
        snapshot = engine.run_next_step()
    prior = dict(snapshot.outputs[AgentNames.FUSION_GENERATION])
    assert snapshot.guardian_retries == 1

    failed = engine.run_next_step()

    assert failed.status == WorkflowStatus.FAILED
    assert failed.failed_agent == AgentNames.FUSION_GENERATION
    assert failed.outputs[AgentNames.FUSION_GENERATION] == prior
    assert failed.execution_records[-1].retryable is True
    assert len(provider.calls) == 2
    assert provider.calls[0]["reference_images"] == [
        str(PROJECT_ROOT / "assets" / "demo" / "ip_reference.jpg")
    ]
    first_prompt = str(provider.calls[0]["prompt"])
    second_prompt = str(provider.calls[1]["prompt"])
    assert "IP_IDENTITY_GRAMMAR" in first_prompt
    assert "IP_ADAPTATION_PLAN" in first_prompt
    assert "BRAND_FEATURE_POOL" in first_prompt
    assert "Revision required:" in second_prompt


def test_frontend_visibly_distinguishes_demo_live_and_unverified_modes() -> None:
    html = (PROJECT_ROOT / "app/ui/frontend/component.html").read_text(encoding="utf-8")
    javascript = (PROJECT_ROOT / "app/ui/frontend/component.js").read_text(
        encoding="utf-8"
    )

    assert 'id="runModeBadge"' in html
    assert 'id="searchModeStatus"' in html
    for label in ("DEMO", "LIVE RUN", "LIVE READY", "UNVERIFIED", "DEMO / MOCK"):
        assert label in javascript
    assert "isRunning && !competitionMode" in javascript
    assert "Luna Demo" in javascript
    assert "Terra Demo" in javascript
