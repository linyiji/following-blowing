from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import (
    AppSettings,
    apply_runtime_provider_config,
    load_settings,
)
from app.services.errors import ImageGenerationError, ProviderError, SearchError

from .base_ai import AIProvider
from .client import ProviderCallMetadata, ProviderCallResult, ProviderClient
from .demo_ai import DemoAIProvider
from .demo_image import DemoImageProvider
from .image_artifact import ImageArtifact, normalize_image_artifact
from .image_base import ImageProvider
from .openai_ai import OpenAIProvider, OpenAIProviderAdapter
from .openai_image import OpenAIImageProvider
from .search_base import SearchProvider, SearchResult
from .search_mock import DemoSearchProvider, MockSearchProvider
from .search_openai import OpenAIWebSearchProvider

if TYPE_CHECKING:
    from app.settings.models import RuntimeProviderConfig


def _resolved_settings(
    settings: AppSettings | "RuntimeProviderConfig",
    runtime_config: "RuntimeProviderConfig | None" = None,
) -> AppSettings:
    """Resolve legacy/admin settings plus an optional highest-priority BYOK overlay."""

    if isinstance(settings, AppSettings):
        return (
            apply_runtime_provider_config(settings, runtime_config)
            if runtime_config is not None
            else settings
        )
    # Direct RuntimeProviderConfig construction is useful at the factory
    # boundary and remains lazy: no OpenAI SDK client is created here.
    if callable(getattr(settings, "api_key_value", None)):
        base = load_settings(environ={})
        return apply_runtime_provider_config(base, settings)  # type: ignore[arg-type]
    raise TypeError("ProviderFactory requires AppSettings or RuntimeProviderConfig")


def create_ai_provider(
    settings: AppSettings | "RuntimeProviderConfig",
    runtime_config: "RuntimeProviderConfig | None" = None,
) -> AIProvider:
    settings = _resolved_settings(settings, runtime_config)
    if settings.demo_mode or settings.multimodal.is_demo:
        return DemoAIProvider()
    if settings.multimodal.provider.lower() == "openai":
        return OpenAIProvider(
            settings.multimodal,
            model_fast=settings.model_fast,
            model_main=settings.model_main,
            client=ProviderClient(
                timeout=settings.multimodal.timeout,
                max_retries=settings.max_provider_retries,
            ),
        )
    raise ProviderError(f"Unsupported multimodal provider: {settings.multimodal.provider}")


def create_image_provider(
    settings: AppSettings | "RuntimeProviderConfig",
    runtime_config: "RuntimeProviderConfig | None" = None,
) -> ImageProvider:
    settings = _resolved_settings(settings, runtime_config)
    if settings.demo_mode or settings.image.is_demo:
        return DemoImageProvider()
    if settings.image.provider.lower() == "openai":
        return OpenAIImageProvider(
            settings.image,
            multi_reference_image_edit=settings.allow_multi_reference_image_edit,
            client=ProviderClient(
                timeout=settings.image.timeout,
                max_retries=min(1, settings.max_provider_retries),
            ),
        )
    raise ImageGenerationError(f"Unsupported image provider: {settings.image.provider}")


def create_search_provider(
    settings: AppSettings | "RuntimeProviderConfig",
    runtime_config: "RuntimeProviderConfig | None" = None,
) -> SearchProvider:
    settings = _resolved_settings(settings, runtime_config)
    if settings.demo_mode or settings.search.is_demo:
        return MockSearchProvider()
    if settings.search.provider.lower() == "openai":
        return OpenAIWebSearchProvider(
            settings.search,
            capability_verified=settings.search_provider_verified,
            client=ProviderClient(
                timeout=settings.search.timeout,
                max_retries=settings.max_provider_retries,
            ),
        )
    raise SearchError(f"Unsupported search provider: {settings.search.provider}")


class ProviderFactory:
    """Single lazy provider construction boundary for all deployment modes."""

    def __init__(
        self,
        settings: AppSettings | "RuntimeProviderConfig",
        runtime_config: "RuntimeProviderConfig | None" = None,
    ) -> None:
        self.settings = _resolved_settings(settings, runtime_config)

    def create_ai(self) -> AIProvider:
        return create_ai_provider(self.settings)

    def create_image(self) -> ImageProvider:
        return create_image_provider(self.settings)

    def create_search(self) -> SearchProvider:
        return create_search_provider(self.settings)


__all__ = [
    "AIProvider",
    "DemoAIProvider",
    "DemoImageProvider",
    "DemoSearchProvider",
    "ImageArtifact",
    "ImageProvider",
    "MockSearchProvider",
    "OpenAIImageProvider",
    "OpenAIProvider",
    "OpenAIProviderAdapter",
    "OpenAIWebSearchProvider",
    "ProviderCallMetadata",
    "ProviderCallResult",
    "ProviderClient",
    "ProviderFactory",
    "SearchProvider",
    "SearchResult",
    "create_ai_provider",
    "create_image_provider",
    "create_search_provider",
    "normalize_image_artifact",
]
