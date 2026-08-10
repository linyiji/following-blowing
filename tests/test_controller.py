from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path

import pytest

from app.config import PROJECT_ROOT, load_settings
from app.controller import ApplicationController
from app.errors import ImageGenerationError
from app.providers.image_base import ImageProvider
from app.schemas import REQUIRED_PACKAGE_FILES, WorkflowStatus
from app.workflow.graph import AgentNames


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def make_controller(tmp_path: Path, **environment: str) -> ApplicationController:
    values = {
        "DATA_DIR": str(tmp_path / "data"),
        "DEMO_MODE": "true",
        **environment,
    }
    settings = load_settings(project_root=PROJECT_ROOT, environ=values)
    return ApplicationController(settings)


def start_demo(controller: ApplicationController):
    assets = controller.bootstrap_demo_assets()
    return controller.start_workflow(
        ip_asset_id=assets["ip"].asset_id,
        brand_asset_id=assets["brand"].asset_id,
        selected_goals=["服装融合", "品牌配色"],
        goal_text="保留原始表情",
        ai_suggestion=None,
        ai_suggestion_adopted=False,
    )


def run_to_terminal(controller: ApplicationController, snapshot):
    while snapshot.status not in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}:
        snapshot = controller.advance_workflow(snapshot.run_id)
    return snapshot


def test_controller_end_to_end_binds_only_guardian_pass_as_final(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    snapshot = start_demo(controller)

    for _ in range(9):
        snapshot = controller.advance_workflow(snapshot.run_id)
    run = controller.repository.get_run(snapshot.run_id)
    assert snapshot.last_completed_agent == AgentNames.FUSION_GENERATION
    assert run["image_generation_calls"] == 1
    assert run["final_candidate_id"] is None
    assert run.get("final_image_path") is None

    snapshot = controller.advance_workflow(snapshot.run_id)
    run = controller.repository.get_run(snapshot.run_id)
    candidate = snapshot.outputs[AgentNames.FUSION_GENERATION]
    assert snapshot.last_completed_agent == AgentNames.IP_GUARDIAN
    assert run["final_candidate_id"] == candidate["candidate_id"]
    assert run["final_image_path"] == "output/result.png"
    assert (controller.repository.run_dir(snapshot.run_id) / "output/result.png").is_file()

    snapshot = run_to_terminal(controller, snapshot)
    assert snapshot.status == WorkflowStatus.COMPLETED
    assert controller.repository.get_run(snapshot.run_id)["search_calls"] == 1
    assert controller.result_payload(snapshot)["image_url"].startswith(
        "data:image/png;base64,"
    )

    package = controller.export_design_package(snapshot.run_id)
    with zipfile.ZipFile(package) as archive:
        assert set(REQUIRED_PACKAGE_FILES) <= set(archive.namelist())
        guide_text = archive.read("design_guide.md").decode("utf-8")
        assert snapshot.outputs[AgentNames.DESIGN_PACKAGE]["copy_description"] in guide_text
        trace_text = archive.read("workflow_trace.json").decode("utf-8")
        assert "/Users/" not in trace_text
        assert str(controller.settings.data_dir) not in trace_text
        assert "ranking.json" in archive.namelist()


def test_export_rejects_incomplete_or_mismatched_completed_checkpoint(
    tmp_path: Path,
) -> None:
    controller = make_controller(tmp_path)
    snapshot = run_to_terminal(controller, start_demo(controller))

    missing_ranking = snapshot.model_copy(deep=True)
    missing_ranking.outputs.pop(AgentNames.RANKING)
    controller.repository.save_checkpoint(snapshot.run_id, missing_ranking)
    with pytest.raises(ValueError, match="Schema-v2 completed workflows are missing outputs"):
        controller.export_design_package(snapshot.run_id)

    mismatched = snapshot.model_copy(deep=True)
    mismatched.outputs[AgentNames.RANKING]["candidate_id"] = "candidate-other"
    controller.repository.save_checkpoint(snapshot.run_id, mismatched)
    with pytest.raises(ValueError, match="same approved candidate"):
        controller.export_design_package(snapshot.run_id)


class FailingImageProvider(ImageProvider):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, **kwargs):
        del kwargs
        self.calls += 1
        raise ImageGenerationError(
            "api_key=DUMMY_PROVIDER_CREDENTIAL at /Users/service/private/result.png"
        )

    def edit_with_reference(self, **kwargs):
        return self.generate(**kwargs)


def test_failed_image_attempts_are_bounded_and_errors_are_redacted(
    tmp_path: Path,
) -> None:
    settings = load_settings(
        project_root=PROJECT_ROOT,
        environ={
            "DATA_DIR": str(tmp_path / "data"),
            "DEMO_MODE": "true",
            "MAX_IMAGE_GENERATIONS_PER_RUN": "3",
        },
    )
    provider = FailingImageProvider()
    controller = ApplicationController(settings, image_provider=provider)
    snapshot = start_demo(controller)
    for _ in range(8):
        snapshot = controller.advance_workflow(snapshot.run_id)

    for attempt in range(4):
        snapshot = controller.advance_workflow(snapshot.run_id)
        assert snapshot.status == WorkflowStatus.FAILED
        if attempt < 3:
            assert controller.repository.get_run(snapshot.run_id)[
                "image_generation_calls"
            ] == attempt + 1
        if attempt < 3:
            snapshot = controller.retry_current_agent(snapshot.run_id)

    assert provider.calls == 3
    assert controller.repository.get_run(snapshot.run_id)["image_generation_calls"] == 3
    public = json.dumps(controller.public_snapshot(snapshot), ensure_ascii=False)
    persisted = "\n".join(
        (controller.repository.run_dir(snapshot.run_id) / name).read_text(
            encoding="utf-8"
        )
        for name in ("run.json", "workflow.json")
    )
    for value in (public, persisted):
        assert "DUMMY_PROVIDER_CREDENTIAL" not in value
        assert "/Users/service" not in value


def test_invalidation_replaces_run_input_and_preserves_historical_retry_count(
    tmp_path: Path,
) -> None:
    controller = make_controller(
        tmp_path,
        MAX_IMAGE_GENERATIONS_PER_RUN="5",
    )
    snapshot = start_demo(controller)
    snapshot.user_intent.metadata["guardian_score_sequence"] = [70, 90]
    controller.repository.save_checkpoint(snapshot.run_id, snapshot)
    snapshot = run_to_terminal(controller, snapshot)
    assert snapshot.status == WorkflowStatus.COMPLETED
    assert controller.repository.get_run(snapshot.run_id)["guardian_regenerations"] == 1

    replacement = controller.assets.ingest(
        PNG,
        filename="replacement.png",
        declared_mime="image/png",
    )
    invalidated = controller.invalidate_run(
        snapshot.run_id,
        "brand_asset",
        brand_asset_id=replacement.asset_id,
    )
    run = controller.repository.get_run(snapshot.run_id)
    input_dir = controller.repository.run_dir(snapshot.run_id) / "input"
    assert invalidated.input_assets.metadata["brand_asset_id"] == replacement.asset_id
    assert (input_dir / "brand.png").read_bytes() == PNG
    assert not (input_dir / "brand.jpg").exists()
    assert run["final_candidate_id"] is None
    assert run["guardian_regenerations"] == 1

    restored_controller = ApplicationController(controller.settings)
    restored = restored_controller.restore_snapshot(snapshot.run_id)
    assert restored.revision == invalidated.revision
    assert restored.input_assets.metadata["brand_asset_id"] == replacement.asset_id
    assert restored_controller.assets.storage.root == controller.settings.assets_dir.resolve()
