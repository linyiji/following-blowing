from __future__ import annotations

import json
import os
import tempfile
import zipfile
from dataclasses import asdict, is_dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from app.config import PROJECT_ROOT
from app.schemas import LEGACY_REQUIRED_PACKAGE_FILES, REQUIRED_PACKAGE_FILES

from .run_service import LocalRunRepository, _jsonable


_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".json", ".md", ".txt"}


def _safe_archive_name(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError("Unsafe package entry name")
    if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported package entry type: {path.suffix}")
    return str(path)


def _content_bytes(value: Any, suffix: str) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, Path):
        if not value.is_file():
            raise FileNotFoundError(value)
        return value.read_bytes()
    if isinstance(value, str):
        possible_path = Path(value)
        if suffix in {".png", ".jpg", ".jpeg", ".webp"} and possible_path.is_file():
            return possible_path.read_bytes()
        return value.encode("utf-8")
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif is_dataclass(value):
        value = asdict(value)
    return json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


class ExportService:
    def __init__(self, repository: LocalRunRepository | None = None) -> None:
        self.repository = repository or LocalRunRepository(PROJECT_ROOT / "data" / "runs")

    def create_zip(self, run_id: str, files: Mapping[str, Any]) -> Path:
        if not files:
            raise ValueError("Cannot create an empty design package")
        run_dir = self.repository.ensure_artifact_layout(run_id)
        destination = run_dir / "output" / f"following-blowing-{run_id}.zip"
        entries: dict[str, bytes] = {}
        for raw_name, value in files.items():
            name = _safe_archive_name(str(raw_name))
            if name in entries:
                raise ValueError(f"Duplicate package entry: {name}")
            entries[name] = _content_bytes(value, PurePosixPath(name).suffix.lower())
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as handle:
            temporary = Path(handle.name)
        try:
            with zipfile.ZipFile(temporary, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, payload in entries.items():
                    archive.writestr(name, payload)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        self.repository.update_run(run_id, design_package_id=destination.name)
        return destination

    def create_design_package(
        self,
        run_id: str,
        *,
        result_image: Path | str | bytes,
        creative_brief: Any | None = None,
        ip_identity: Any | None = None,
        ip_identity_grammar: Any | None = None,
        brand_profile: Any | None = None,
        brand_feature_pool: Any | None = None,
        fusion_strategy: Any | None = None,
        ip_adaptation: Any | None = None,
        guardian_report: Any | None = None,
        ranking: Any | None = None,
        workflow_trace: Any | None = None,
        design_guide: Any | None = None,
        prompt_trace: Any | None = None,
        additional_files: Mapping[str, Any] | None = None,
        package_schema_version: int = 2,
    ) -> Path:
        if package_schema_version < 1:
            raise ValueError("package_schema_version must be positive")
        if isinstance(result_image, (Path, str)) and Path(result_image).is_file():
            suffix = Path(result_image).suffix.lower()
        else:
            suffix = ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("Final result must be a real PNG, JPEG, or WebP image")
        files: dict[str, Any] = {f"result{suffix}": result_image}
        values = {
            "creative_brief.json": creative_brief,
            "ip_identity_grammar.json": ip_identity_grammar,
            "ip_identity.json": ip_identity,
            "brand_profile.json": brand_profile,
            "brand_feature_pool.json": brand_feature_pool,
            "fusion_strategy.json": fusion_strategy,
            "ip_adaptation.json": ip_adaptation,
            "guardian_report.json": guardian_report,
            "ranking.json": ranking,
            "workflow_trace.json": workflow_trace,
            "design_guide.md": design_guide,
            "prompt_trace.json": prompt_trace,
        }
        required = (
            REQUIRED_PACKAGE_FILES
            if package_schema_version >= 2
            else LEGACY_REQUIRED_PACKAGE_FILES
        )
        required_metadata = set(required) - {"result.png"}
        missing_payloads = sorted(
            name for name in required_metadata if values.get(name) is None
        )
        if missing_payloads:
            raise ValueError(
                "Design package is missing required payloads: "
                f"{missing_payloads}"
            )
        files.update({name: value for name, value in values.items() if value is not None})
        if additional_files:
            files.update(additional_files)
        package = self.create_zip(run_id, files)
        with zipfile.ZipFile(package) as archive:
            entries = set(archive.namelist())
        missing_entries = required_metadata - entries
        has_result = any(
            name in entries
            for name in ("result.png", "result.jpg", "result.jpeg", "result.webp")
        )
        if missing_entries or not has_result:
            raise RuntimeError(
                "Created design package failed its artifact contract"
            )
        return package

    # Convenient name for DesignPackageAgent integrations.
    build_package = create_design_package


__all__ = ["ExportService"]
