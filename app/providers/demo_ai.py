from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from app.services.structured_output import StructuredOutputService

from .base_ai import AIProvider, ImageInput


def _schema_for(model: type) -> dict[str, Any]:
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()  # type: ignore[no-any-return,attr-defined]
    if hasattr(model, "schema"):
        return model.schema()  # type: ignore[no-any-return,attr-defined]
    return {}


def _demo_from_schema(schema: Mapping[str, Any], *, field_name: str = "value") -> Any:
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]
    for branch in schema.get("anyOf", []) or schema.get("oneOf", []):
        if branch.get("type") != "null":
            return _demo_from_schema(branch, field_name=field_name)
    value_type = schema.get("type")
    if value_type == "object" or schema.get("properties"):
        required = set(schema.get("required", []))
        return {
            key: _demo_from_schema(value, field_name=key)
            for key, value in schema.get("properties", {}).items()
            if key in required or "default" in value
        }
    if value_type == "array":
        minimum = int(schema.get("minItems", 0) or 0)
        item = schema.get("items", {})
        return [_demo_from_schema(item, field_name=field_name) for _ in range(minimum)]
    if value_type == "boolean":
        return True
    if value_type == "integer":
        return int(schema.get("minimum", 0))
    if value_type == "number":
        return float(schema.get("minimum", 0.0))
    if field_name == "status":
        return "completed"
    if field_name.endswith("_id"):
        return f"demo_{field_name}"
    return f"Demo {field_name.replace('_', ' ')}"


class DemoAIProvider(AIProvider):
    """Deterministic provider using the same interface as real adapters."""

    def __init__(self, fixtures: Mapping[str, Any] | None = None) -> None:
        self.fixtures = dict(fixtures or {})
        self.structured_output = StructuredOutputService(max_repairs=0)

    def _fixture(self, prompt: str, context: Mapping[str, Any] | None = None) -> Any:
        fixture_key = str((context or {}).get("fixture_key", ""))
        if fixture_key and fixture_key in self.fixtures:
            return self.fixtures[fixture_key]
        for key, value in self.fixtures.items():
            if key and key in prompt:
                return value
        return None

    def generate_text(
        self,
        *,
        prompt: str,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        demo_output = kwargs.pop("demo_output", None)
        del kwargs
        fixture = self._fixture(prompt, context)
        if fixture is not None:
            return fixture if isinstance(fixture, str) else json.dumps(fixture, ensure_ascii=False)
        if demo_output is not None:
            return (
                demo_output
                if isinstance(demo_output, str)
                else json.dumps(demo_output, ensure_ascii=False)
            )
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
        return f"Demo response [{digest}]"

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        demo_output = kwargs.pop("demo_output", None)
        del kwargs
        fixture = self._fixture(prompt, context)
        if fixture is None:
            fixture = demo_output
        if fixture is None and context:
            # Legacy compatibility for callers that embedded demo fixtures in context.
            fixture = context.get("demo_output")
        if fixture is None:
            fixture = _demo_from_schema(_schema_for(response_model))
        return self.structured_output.parse(fixture, response_model)

    def analyze_multimodal(
        self,
        *,
        images: Sequence[ImageInput],
        prompt: str,
        response_model: type | None = None,
        **kwargs: Any,
    ) -> Any:
        del images
        context = kwargs.pop("context", None)
        if response_model is None:
            return self.generate_text(prompt=prompt, context=context, **kwargs)
        return self.generate_structured(
            prompt=prompt,
            response_model=response_model,
            context=context,
            **kwargs,
        )


__all__ = ["DemoAIProvider"]
