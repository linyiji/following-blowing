from __future__ import annotations

import base64
import zipfile

from app.schemas import DesignPackage
from app.services.export_service import ExportService
from app.services.run_service import LocalRunRepository


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_design_package_uses_following_blowing_default_name():
    package = DesignPackage(result_image_uri="result.png")

    assert package.package_name == "following-blowing-design-package.zip"


def test_export_service_creates_real_run_specific_zip(tmp_path):
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run()
    service = ExportService(repository)
    package = service.create_design_package(
        run["run_id"],
        result_image=PNG,
        creative_brief={"theme": "Demo"},
        ip_identity={"compatibility": True},
        ip_identity_grammar={"anchors": ["face"]},
        brand_profile={"brand": "Demo"},
        brand_feature_pool={"features": ["product"]},
        fusion_strategy={"depth": "PRODUCT_INTERACTION"},
        ip_adaptation={"target_pose": "seated"},
        guardian_report={"status": "PASS", "score": 90},
        ranking={"total_score": 88},
        workflow_trace={"agents": 12},
        design_guide="# Design guide\n",
        prompt_trace={"version": "3.0.0"},
    )

    assert package.name == f"following-blowing-{run['run_id']}.zip"
    assert repository.get_run(run["run_id"])["design_package_id"] == package.name
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert {
            "result.png",
            "creative_brief.json",
            "ip_identity_grammar.json",
            "brand_feature_pool.json",
            "ip_adaptation.json",
            "guardian_report.json",
            "ranking.json",
            "design_guide.md",
        } <= names
        assert archive.read("result.png") == PNG


def test_schema_v2_export_rejects_missing_required_payloads(tmp_path):
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run()
    service = ExportService(repository)

    try:
        service.create_design_package(
            run["run_id"],
            result_image=PNG,
            creative_brief={"theme": "Incomplete"},
        )
    except ValueError as exc:
        assert "missing required payloads" in str(exc)
    else:
        raise AssertionError("incomplete schema-v2 package was accepted")


def test_schema_v1_export_retains_historical_package_contract(tmp_path):
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run()
    service = ExportService(repository)
    package = service.create_design_package(
        run["run_id"],
        result_image=PNG,
        creative_brief={"theme": "Historical"},
        ip_identity={"identity_lock": {"legacy": True}},
        brand_profile={"brand": "Historical"},
        fusion_strategy={"logic": "legacy"},
        guardian_report={"status": "PASS", "score": 90},
        ranking={"total_score": 88},
        workflow_trace={"schema": 1},
        design_guide="# Historical design guide\n",
        prompt_trace={"legacy": True},
        package_schema_version=1,
    )

    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
    assert "ip_identity.json" in names
    assert "ip_identity_grammar.json" not in names
    assert "ip_adaptation.json" not in names


def test_export_rejects_fake_or_unsafe_formats(tmp_path):
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run()
    service = ExportService(repository)
    try:
        service.create_zip(run["run_id"], {"../fake.ai": b"not an illustrator file"})
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe/fake package entry was accepted")
