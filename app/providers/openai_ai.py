from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.config import MODEL_FAST, MODEL_MAIN, ProviderSettings
from app.services.errors import ProviderError
from app.services.structured_output import StructuredOutputService

from .base_ai import AIProvider, ImageInput
from .client import ProviderClient


def _schema_for(model: type) -> dict[str, Any]:
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()  # type: ignore[no-any-return,attr-defined]
    if hasattr(model, "schema"):
        return model.schema()  # type: ignore[no-any-return,attr-defined]
    return {}


class OpenAIProvider(AIProvider):
    """Responses API adapter with explicit fast/main model routing."""

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        model_fast: str = MODEL_FAST,
        model_main: str | None = None,
        client: ProviderClient | None = None,
    ) -> None:
        self.settings = settings
        self.model_fast = model_fast
        self.model_main = model_main or settings.model or MODEL_MAIN
        self.provider_client = client or ProviderClient(timeout=settings.timeout)
        self.structured_output = StructuredOutputService(max_repairs=0)
        self._sdk_client: Any | None = None

    def _require_sdk(self) -> Any:
        if not self.settings.api_key or not self.model_fast or not self.model_main:
            raise ProviderError("OpenAI multimodal provider is not configured")
        if self._sdk_client is None:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError as exc:
                raise ProviderError("OpenAI SDK is not installed") from exc
            self._sdk_client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=self.settings.timeout,
                # ProviderClient is the single retry governor. Leaving the SDK
                # default enabled multiplies worst-case latency invisibly.
                max_retries=0,
            )
        return self._sdk_client

    def _model_for_role(self, role: str | None) -> str:
        normalized = (role or "main").strip().lower()
        routes = {"fast": self.model_fast, "main": self.model_main}
        try:
            return routes[normalized]
        except KeyError as exc:
            raise ProviderError(f"Unsupported AI model role: {normalized}") from exc

    @staticmethod
    def _output_text(response: Any) -> str:
        output = getattr(response, "output_text", None)
        if output:
            return str(output)
        if isinstance(response, Mapping) and response.get("output_text"):
            return str(response["output_text"])
        raise ProviderError("OpenAI response did not contain text")

    @staticmethod
    def _response_has_refusal(response: Any) -> bool:
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "refusal":
                    return True
        return False

    def _responses_create(self, input_value: Any, model: str) -> Any:
        sdk = self._require_sdk()
        responses = getattr(sdk, "responses", None)
        if responses is None or not hasattr(responses, "create"):
            raise ProviderError("Configured OpenAI client does not support the Responses API")
        return responses.create(model=model, input=input_value)

    def _responses_parse(self, input_value: Any, response_model: type, model: str) -> Any:
        sdk = self._require_sdk()
        responses = getattr(sdk, "responses", None)
        if responses is None or not hasattr(responses, "parse"):
            raise ProviderError("Configured OpenAI client does not support Structured Outputs")
        return responses.parse(model=model, input=input_value, text_format=response_model)

    def _parsed_output(self, response: Any, response_model: type) -> Any:
        if getattr(response, "status", None) == "incomplete":
            raise ProviderError("OpenAI structured response was incomplete")
        if self._response_has_refusal(response):
            raise ProviderError("OpenAI refused the structured request")
        parsed = getattr(response, "output_parsed", None)
        if parsed is None and isinstance(response, Mapping):
            parsed = response.get("output_parsed")
        if parsed is None:
            # Compatibility for Responses-compatible gateways that return valid
            # JSON text but omit the SDK convenience property.
            raw = self._output_text(response)
            return self.structured_output.parse(raw, response_model)
        if isinstance(parsed, response_model):
            return parsed
        if hasattr(response_model, "model_validate"):
            return response_model.model_validate(parsed)
        return self.structured_output.parse(parsed, response_model)

    @staticmethod
    def _structured_prompt(prompt: str, response_model: type) -> str:
        schema = _schema_for(response_model)
        return (
            f"{prompt}\n\n"
            "Return ONLY one valid JSON object matching the JSON Schema below. "
            "Use the exact property names. Do not translate, rename, omit, or add fields. "
            "Do not use Markdown or code fences.\n\n"
            f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _safe_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
        # Demo fixtures are adapter-local and must never be sent to a real model.
        return {
            str(key): value
            for key, value in (context or {}).items()
            if str(key) not in {"demo_output", "fixture_key"}
        }

    def generate_text(
        self,
        *,
        prompt: str,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        model = self._model_for_role(kwargs.pop("model_role", None))
        kwargs.pop("demo_output", None)
        effective_prompt = prompt
        safe_context = self._safe_context(context)
        if safe_context:
            effective_prompt = (
                f"{effective_prompt}\n\nContext JSON:\n"
                f"{json.dumps(safe_context, ensure_ascii=False, default=str)}"
            )
        response = self.provider_client.execute(
            "ai.generate_text",
            self._responses_create,
            effective_prompt,
            model,
        )
        return self._output_text(response)

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        model = self._model_for_role(kwargs.pop("model_role", None))
        kwargs.pop("demo_output", None)
        safe_context = self._safe_context(context)
        effective_prompt = self._structured_prompt(prompt, response_model)
        if safe_context:
            effective_prompt = (
                f"{effective_prompt}\n\nContext JSON:\n"
                f"{json.dumps(safe_context, ensure_ascii=False, default=str)}"
            )
        response = self.provider_client.execute(
            "ai.generate_structured",
            self._responses_parse,
            effective_prompt,
            response_model,
            model,
        )
        return self._parsed_output(response, response_model)

    @staticmethod
    def _image_content(image: ImageInput, *, detail: str = "high") -> dict[str, Any]:
        if isinstance(image, bytes):
            encoded = base64.b64encode(image).decode("ascii")
            url = f"data:image/png;base64,{encoded}"
        else:
            value = str(image)
            path = Path(value)
            if path.is_file():
                mime = mimetypes.guess_type(path.name)[0] or "image/png"
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                url = f"data:{mime};base64,{encoded}"
            elif value.startswith(("https://", "data:image/")):
                url = value
            else:
                raise ProviderError(
                    "Multimodal image input must be bytes, a local file, or an HTTPS URL"
                )
        if detail not in {"low", "high", "auto"}:
            raise ValueError(f"Unsupported image detail: {detail}")
        return {"type": "input_image", "image_url": url, "detail": detail}

    def analyze_multimodal(
        self,
        *,
        images: Sequence[ImageInput],
        prompt: str,
        response_model: type | None = None,
        **kwargs: Any,
    ) -> Any:
        model = self._model_for_role(kwargs.pop("model_role", None))
        image_detail = str(kwargs.pop("image_detail", "high")).lower()
        kwargs.pop("demo_output", None)
        effective_prompt = (
            self._structured_prompt(prompt, response_model)
            if response_model is not None
            else prompt
        )
        content: list[dict[str, Any]] = [
            {"type": "input_text", "text": effective_prompt}
        ]
        content.extend(
            self._image_content(item, detail=image_detail) for item in images
        )
        input_value = [{"role": "user", "content": content}]

        if response_model is None:
            response = self.provider_client.execute(
                "ai.analyze_multimodal",
                self._responses_create,
                input_value,
                model,
            )
            return self._output_text(response)

        response = self.provider_client.execute(
            "ai.analyze_multimodal_structured",
            self._responses_parse,
            input_value,
            response_model,
            model,
        )
        return self._parsed_output(response, response_model)


# Backward-compatible explicit name used by some integrations.
OpenAIProviderAdapter = OpenAIProvider


__all__ = ["OpenAIProvider", "OpenAIProviderAdapter"]
