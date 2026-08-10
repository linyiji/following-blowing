"""Opt-in, browser-safe connection checks for OpenAI-compatible BYOK providers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import RuntimeProviderConfig


class ConnectionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["provider", "fast", "main", "image"]
    status: Literal["pass", "fail", "unverified"]
    model: str | None = None
    message: str


class ConnectionTestResult(BaseModel):
    """Safe result suitable for Components v2; it can never contain a key."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    provider_reachable: bool = False
    catalog_supported: bool = False
    image_generation_performed: bool = False
    checks: list[ConnectionCheck] = Field(default_factory=list)
    error_code: str | None = None
    message: str

    def public_view(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _safe_error(exc: Exception, *, stage: str) -> tuple[str, str]:
    """Classify an SDK error without returning its body, URL, or traceback."""

    status = getattr(exc, "status_code", None)
    if status in {401, 403}:
        return "authentication_failed", "Authentication failed. Check the API credential."
    if status == 404 and stage in {"fast", "main", "image"}:
        return "model_unavailable", f"The configured {stage} model is unavailable."
    if status == 429:
        return "rate_limited", "Provider rate limit reached. Try again later."
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "provider_unreachable", "Provider could not be reached within the timeout."
    # Never echo arbitrary exception text from an SDK/gateway.
    return "connection_failed", f"The {stage} connection check failed ({type(exc).__name__})."


class ProviderConnectionTester:
    """Run tiny text/catalog checks; image generation is explicit and separate."""

    def __init__(
        self,
        client_factory: Callable[[RuntimeProviderConfig], Any] | None = None,
    ) -> None:
        self._client_factory = client_factory or self._default_client

    @staticmethod
    def _default_client(config: RuntimeProviderConfig) -> Any:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency deployment failure
            raise RuntimeError("OpenAI SDK unavailable") from exc
        key = config.api_key_value()
        if not key:
            raise ValueError("API credential is not configured")
        return OpenAI(
            api_key=key,
            base_url=config.base_url,
            timeout=max(config.fast_timeout, config.main_timeout),
        )

    @staticmethod
    def _catalog(client: Any) -> tuple[bool, set[str]]:
        models = getattr(client, "models", None)
        if models is None or not callable(getattr(models, "list", None)):
            return False, set()
        response = models.list()
        values = getattr(response, "data", response)
        identifiers: set[str] = set()
        for value in values or []:
            identifier = getattr(value, "id", None)
            if identifier is None and isinstance(value, dict):
                identifier = value.get("id")
            if identifier:
                identifiers.add(str(identifier))
        return True, identifiers

    @staticmethod
    def _tiny_text(client: Any, *, model: str) -> None:
        responses = getattr(client, "responses", None)
        create = getattr(responses, "create", None)
        if not callable(create):
            raise RuntimeError("Responses API unavailable")
        create(model=model, input="Reply with OK.")

    def test(self, config: RuntimeProviderConfig) -> ConnectionTestResult:
        """Test catalog plus Fast/Main text. This method never calls an image API."""

        if not config.has_api_key:
            return ConnectionTestResult(
                ok=False,
                checks=[
                    ConnectionCheck(
                        name="provider",
                        status="fail",
                        message="API credential is not configured.",
                    )
                ],
                error_code="authentication_missing",
                message="Enter an API credential before testing the connection.",
            )

        checks: list[ConnectionCheck] = []
        try:
            client = self._client_factory(config)
        except Exception as exc:
            code, message = _safe_error(exc, stage="provider")
            return ConnectionTestResult(
                ok=False,
                checks=[ConnectionCheck(name="provider", status="fail", message=message)],
                error_code=code,
                message=message,
            )

        catalog_supported = False
        catalog: set[str] = set()
        try:
            catalog_supported, catalog = self._catalog(client)
            checks.append(
                ConnectionCheck(
                    name="provider",
                    status="pass",
                    message="Provider reachable.",
                )
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status in {404, 405, 501} or isinstance(exc, (AttributeError, NotImplementedError)):
                checks.append(
                    ConnectionCheck(
                        name="provider",
                        status="unverified",
                        message="Model catalog is not supported; text checks will continue.",
                    )
                )
            else:
                code, message = _safe_error(exc, stage="provider")
                return ConnectionTestResult(
                    ok=False,
                    checks=[ConnectionCheck(name="provider", status="fail", message=message)],
                    error_code=code,
                    message=message,
                )

        for stage, model in (("fast", config.model_fast), ("main", config.model_main)):
            if catalog_supported and model not in catalog:
                checks.append(
                    ConnectionCheck(
                        name=stage,  # type: ignore[arg-type]
                        status="fail",
                        model=model,
                        message=f"Configured {stage} model is not in the provider catalog.",
                    )
                )
                return ConnectionTestResult(
                    ok=False,
                    provider_reachable=True,
                    catalog_supported=True,
                    checks=checks,
                    error_code="model_unavailable",
                    message=f"The configured {stage} model is unavailable.",
                )
            try:
                self._tiny_text(client, model=model)
                checks.append(
                    ConnectionCheck(
                        name=stage,  # type: ignore[arg-type]
                        status="pass",
                        model=model,
                        message=f"{stage.title()} text check passed.",
                    )
                )
            except Exception as exc:
                code, message = _safe_error(exc, stage=stage)
                checks.append(
                    ConnectionCheck(
                        name=stage,  # type: ignore[arg-type]
                        status="fail",
                        model=model,
                        message=message,
                    )
                )
                return ConnectionTestResult(
                    ok=False,
                    provider_reachable=True,
                    catalog_supported=catalog_supported,
                    checks=checks,
                    error_code=code,
                    message=message,
                )

        image_status: Literal["pass", "unverified"] = (
            "pass" if catalog_supported and config.image_model in catalog else "unverified"
        )
        image_message = (
            "Image model found in the provider catalog; no image was generated."
            if image_status == "pass"
            else "Image model configured; no image was generated during this test."
        )
        checks.append(
            ConnectionCheck(
                name="image",
                status=image_status,
                model=config.image_model,
                message=image_message,
            )
        )
        if catalog_supported and image_status != "pass":
            return ConnectionTestResult(
                ok=False,
                provider_reachable=True,
                catalog_supported=True,
                checks=checks,
                error_code="model_unavailable",
                message="The configured image model is unavailable.",
            )
        return ConnectionTestResult(
            ok=True,
            provider_reachable=True,
            catalog_supported=catalog_supported,
            checks=checks,
            message="Provider, Fast, and Main checks passed. No image was generated.",
        )

    def test_image(self, config: RuntimeProviderConfig) -> ConnectionTestResult:
        """Explicit paid image probe. Never called by :meth:`test`."""

        if not config.has_api_key:
            return ConnectionTestResult(
                ok=False,
                error_code="authentication_missing",
                message="Enter an API credential before the advanced image test.",
            )
        try:
            client = self._client_factory(config)
            images = getattr(client, "images", None)
            generate = getattr(images, "generate", None)
            if not callable(generate):
                raise RuntimeError("Images API unavailable")
            generate(
                model=config.image_model,
                prompt="A single neutral blue circle on a white background.",
                size="1024x1024",
            )
        except Exception as exc:
            code, message = _safe_error(exc, stage="image")
            return ConnectionTestResult(
                ok=False,
                image_generation_performed=True,
                checks=[
                    ConnectionCheck(
                        name="image",
                        status="fail",
                        model=config.image_model,
                        message=message,
                    )
                ],
                error_code=code,
                message=message,
            )
        return ConnectionTestResult(
            ok=True,
            provider_reachable=True,
            image_generation_performed=True,
            checks=[
                ConnectionCheck(
                    name="image",
                    status="pass",
                    model=config.image_model,
                    message="Advanced image test passed.",
                )
            ],
            message="Advanced image test passed and may have incurred provider charges.",
        )


__all__ = [
    "ConnectionCheck",
    "ConnectionTestResult",
    "ProviderConnectionTester",
]
