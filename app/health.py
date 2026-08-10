from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.config import AppSettings, load_settings
from app.documents import DocumentReader


@dataclass(frozen=True, slots=True)
class HealthStatus:
    frontend_ready: bool
    document_reader_ready: bool
    multimodal_provider_ready: bool
    model_catalog_verified: bool
    luna_ready: bool
    terra_ready: bool
    image_provider_ready: bool
    image_provider_configured: bool
    image_provider_verified: bool
    search_provider_ready: bool
    search_mode: str
    provider_mode: str
    competition_mode: bool
    multi_reference_image_edit: str
    demo_mode: bool
    status: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AppBootstrap:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()

    def ensure_directories(self) -> None:
        root = self.settings.project_root
        for path in (
            self.settings.data_dir,
            self.settings.runs_dir,
            self.settings.assets_dir,
            self.settings.data_dir / "documents",
            self.settings.data_dir / "generated",
            root / "assets" / "demo",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def check(self) -> HealthStatus:
        root = self.settings.project_root
        warnings: list[str] = []
        frontend_files = [
            root / "app" / "ui" / "frontend" / "component.html",
            root / "app" / "ui" / "frontend" / "component.css",
            root / "app" / "ui" / "frontend" / "component.js",
        ]
        frontend_ready = all(path.is_file() for path in frontend_files)
        if not frontend_ready:
            warnings.append("frontend_assets_missing")

        try:
            DocumentReader()
            document_reader_ready = self.settings.document_parser == "local"
        except Exception:
            document_reader_ready = False
            warnings.append("document_reader_unavailable")

        multimodal_ready = self.settings.demo_mode or self.settings.multimodal.configured
        byok_runtime = getattr(self.settings, "provider_source", "") == "byok"
        model_catalog_ready = (
            self.settings.demo_mode
            or self.settings.model_catalog_verified
            or byok_runtime
        )
        luna_ready = (
            multimodal_ready and bool(self.settings.model_fast) and model_catalog_ready
        )
        terra_ready = (
            multimodal_ready and bool(self.settings.model_main) and model_catalog_ready
        )
        image_configured = self.settings.demo_mode or self.settings.image.configured
        image_ready = (
            self.settings.demo_mode
            or self.settings.image.is_demo
            or (
                self.settings.image.configured
                and (self.settings.image_provider_verified or byok_runtime)
            )
        )
        search_ready = self.settings.search_mode in {"demo", "live"}
        if not self.settings.multimodal.configured:
            warnings.append("multimodal_provider_not_configured_using_demo")
        elif (
            not self.settings.demo_mode
            and not self.settings.model_catalog_verified
            and not byok_runtime
        ):
            warnings.append("provider_model_catalog_unverified")
        if not self.settings.image.configured:
            warnings.append("image_provider_not_configured_using_demo")
        elif not self.settings.demo_mode and not self.settings.image.is_demo and not image_ready:
            warnings.append("image_provider_real_smoke_unverified")
        if not self.settings.search.configured:
            warnings.append("search_provider_not_configured_using_demo")
        elif self.settings.search_mode == "demo":
            warnings.append("search_provider_demo_mock_research")
        elif self.settings.search_mode == "unverified":
            warnings.append("search_provider_capability_unverified")

        required_prompts = root / "app" / "prompts"
        if not required_prompts.is_dir() or not any(required_prompts.glob("*.md")):
            warnings.append("prompt_files_missing")
        demo_assets = root / "assets" / "demo"
        if not demo_assets.is_dir() or not any(demo_assets.iterdir()):
            warnings.append("demo_assets_missing")

        core_ready = (
            frontend_ready
            and document_reader_ready
            and luna_ready
            and terra_ready
            and image_ready
            and search_ready
        )
        status = "READY" if core_ready else "DEGRADED"
        if self.settings.demo_mode and core_ready:
            status = "DEMO_MODE"
        return HealthStatus(
            frontend_ready=frontend_ready,
            document_reader_ready=document_reader_ready,
            multimodal_provider_ready=multimodal_ready,
            model_catalog_verified=self.settings.model_catalog_verified,
            luna_ready=luna_ready,
            terra_ready=terra_ready,
            image_provider_ready=image_ready,
            image_provider_configured=image_configured,
            image_provider_verified=self.settings.image_provider_verified,
            search_provider_ready=search_ready,
            search_mode=self.settings.search_mode,
            provider_mode=self.settings.provider_mode,
            competition_mode=self.settings.competition_mode,
            multi_reference_image_edit=self.settings.multi_reference_image_edit_status,
            demo_mode=self.settings.demo_mode,
            status=status,
            warnings=warnings,
        )

    def run(self) -> HealthStatus:
        self.ensure_directories()
        return self.check()


def check_health(settings: AppSettings | None = None) -> dict[str, Any]:
    return AppBootstrap(settings).run().to_dict()


__all__ = ["AppBootstrap", "HealthStatus", "check_health"]
