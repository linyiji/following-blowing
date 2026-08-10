from __future__ import annotations

from app.services.run_service import LocalRunRepository


def test_run_repository_creates_layout_and_restores_checkpoint(tmp_path):
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run(selected_goals=["服装融合"])

    run_dir = repository.run_dir(run["run_id"])
    assert all((run_dir / name).is_dir() for name in repository.ARTIFACT_DIRECTORIES)
    repository.save_checkpoint(run["run_id"], {"current_step": 2})

    reloaded = LocalRunRepository(tmp_path / "runs")
    assert reloaded.get_run(run["run_id"])["selected_goals"] == ["服装融合"]
    assert reloaded.get_checkpoint(run["run_id"]) == {"current_step": 2}


def test_invalidation_understands_ui_agent_names(tmp_path):
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run()
    run_id = run["run_id"]
    repository.update_run(
        run_id,
        status="COMPLETED",
        agent_results={
            "01 IP Preparation Agent": {"status": "completed"},
            "Brand Intelligence Agent": {"status": "completed"},
            "Creative Brief Agent": {"status": "completed"},
            "Ranking Agent": {"status": "completed"},
        },
        final_candidate_id="candidate_01",
    )

    invalidated = repository.invalidate_dependencies(run_id, "ip_asset_id")
    restored = repository.get_run(run_id)
    assert "ip_preparation" in invalidated
    assert "ip_adaptation" in invalidated
    assert "design_package" in invalidated
    assert "Brand Intelligence Agent" in restored["agent_results"]
    assert "01 IP Preparation Agent" not in restored["agent_results"]
    assert "Creative Brief Agent" not in restored["agent_results"]
    assert restored["final_candidate_id"] is None
    assert restored["status"] == "READY"


def test_repository_redacts_secrets_and_blocks_artifact_traversal(tmp_path):
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run(api_key="must-not-be-written")
    assert repository.get_run(run["run_id"])["api_key"] == "[REDACTED]"
    try:
        repository.write_artifact(run["run_id"], "../escape.txt", "bad")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal was accepted")
