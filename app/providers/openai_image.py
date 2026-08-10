from __future__ import annotations

import base64
import binascii
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Sequence

from app.config import PROJECT_ROOT, ProviderSettings
from app.services.errors import ImageGenerationError, ProviderError

from .client import ProviderClient
from .image_artifact import ImageArtifact, normalize_image_artifact
from .image_base import ImageInput, ImageOutput, ImageProvider


class OpenAIImageProvider(ImageProvider):
    def __init__(
        self,
        settings: ProviderSettings,
        *,
        client: ProviderClient | None = None,
        multi_reference_image_edit: bool = False,
    ) -> None:
        self.settings = settings
        self.provider_client = client or ProviderClient(timeout=settings.timeout, max_retries=1)
        self.multi_reference_image_edit = bool(multi_reference_image_edit)
        self.multi_reference_image_edit_status = (
            "VERIFIED" if self.multi_reference_image_edit else "UNVERIFIED"
        )
        self._sdk_client: Any | None = None

    def _require_sdk(self) -> Any:
        if not self.settings.api_key or not self.settings.model:
            raise ImageGenerationError("OpenAI image provider is not configured")
        if self._sdk_client is None:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError as exc:
                raise ImageGenerationError("OpenAI SDK is not installed") from exc
            self._sdk_client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=self.settings.timeout,
            )
        return self._sdk_client

    @staticmethod
    def _result_bytes(result: Any, timeout: int) -> bytes:
        try:
            item = result.data[0]
        except (AttributeError, IndexError, TypeError) as exc:
            raise ImageGenerationError("Image provider response contained no image") from exc
        encoded = getattr(item, "b64_json", None)
        if encoded:
            try:
                return base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ImageGenerationError("Image provider returned invalid base64") from exc
        url = getattr(item, "url", None)
        if isinstance(url, str) and url.startswith("https://"):
            try:
                with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec B310 - HTTPS checked
                    return response.read(25 * 1024 * 1024 + 1)
            except OSError as exc:
                raise ImageGenerationError("Generated image download failed") from exc
        raise ImageGenerationError("Image provider response did not contain image bytes")

    def _save(
        self,
        result: Any,
        output_path: Path | None,
        *,
        request_id: str,
        latency_ms: int,
    ) -> ImageArtifact:
        data = self._result_bytes(result, self.settings.timeout)
        if len(data) > 25 * 1024 * 1024:
            raise ImageGenerationError("Generated image exceeded the safety limit")
        destination = Path(output_path or PROJECT_ROOT / "data" / "generated" / "generated.png").resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        response_request_id = getattr(result, "_request_id", None) or getattr(
            result, "request_id", None
        )
        return normalize_image_artifact(
            destination,
            relative_to=PROJECT_ROOT,
            provider=self.settings.provider,
            model=str(self.settings.model),
            request_id=str(response_request_id or request_id),
            latency_ms=latency_ms,
        )

    def generate(self, *, prompt: str, output_path: Path | None = None, **kwargs: Any) -> ImageOutput:
        sdk = self._require_sdk()
        request = {"model": self.settings.model, "prompt": prompt}
        request.update({key: value for key, value in kwargs.items() if key in {"size", "quality", "background"}})
        try:
            call = self.provider_client.call("image.generate", sdk.images.generate, **request)
        except ProviderError as exc:
            raise ImageGenerationError(
                "Image generation provider request failed",
                request_id=exc.request_id,
                retryable=True,
            ) from exc
        return self._save(
            call.value,
            output_path,
            request_id=call.metadata.request_id,
            latency_ms=call.metadata.latency_ms,
        )

    def edit_with_reference(
        self,
        *,
        reference_images: Sequence[ImageInput],
        prompt: str,
        output_path: Path | None = None,
        **kwargs: Any,
    ) -> ImageOutput:
        if not reference_images:
            raise ImageGenerationError("At least one reference image is required")
        if len(reference_images) > 1 and not self.multi_reference_image_edit:
            raise ImageGenerationError(
                "Multiple reference image editing is not verified for this provider"
            )
        sdk = self._require_sdk()
        with ExitStack() as stack:
            image_files: list[Any] = []
            for image in reference_images:
                if not isinstance(image, (Path, str)) or not Path(image).is_file():
                    raise ImageGenerationError("OpenAI image editing currently requires local reference files")
                image_files.append(stack.enter_context(Path(image).open("rb")))
            request_image: Any = image_files if len(image_files) > 1 else image_files[0]
            request = {"model": self.settings.model, "prompt": prompt, "image": request_image}
            request.update({key: value for key, value in kwargs.items() if key in {"size", "quality"}})
            try:
                call = self.provider_client.call("image.edit", sdk.images.edit, **request)
            except ProviderError as exc:
                raise ImageGenerationError(
                    "Image edit provider request failed",
                    request_id=exc.request_id,
                    retryable=True,
                ) from exc
            except Exception as exc:
                raise ImageGenerationError("Image edit failed") from exc
        return self._save(
            call.value,
            output_path,
            request_id=call.metadata.request_id,
            latency_ms=call.metadata.latency_ms,
        )


__all__ = ["OpenAIImageProvider"]
