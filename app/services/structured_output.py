from __future__ import annotations

import json
import re
from dataclasses import is_dataclass
from typing import Any, Callable, Generic, Mapping, TypeVar

from .errors import ProviderError


T = TypeVar("T")
RepairFunction = Callable[[Any, Exception], Any]


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    candidate = value.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return value


def validate_structured(value: Any, response_model: type[T]) -> T:
    parsed = _json_value(value)
    if isinstance(parsed, response_model):
        return parsed
    if hasattr(response_model, "model_validate"):
        return response_model.model_validate(parsed)  # type: ignore[no-any-return,attr-defined]
    if hasattr(response_model, "parse_obj"):
        return response_model.parse_obj(parsed)  # type: ignore[no-any-return,attr-defined]
    if is_dataclass(response_model):
        if not isinstance(parsed, Mapping):
            raise TypeError("Dataclass structured output must be an object")
        return response_model(**dict(parsed))  # type: ignore[return-value,call-arg]
    if isinstance(parsed, Mapping):
        return response_model(**dict(parsed))  # type: ignore[return-value,call-arg]
    return response_model(parsed)  # type: ignore[return-value,call-arg]


class StructuredOutputService(Generic[T]):
    """Validate structured output and allow at most one repair attempt."""

    def __init__(self, *, max_repairs: int = 1) -> None:
        if max_repairs not in {0, 1}:
            raise ValueError("Structured output repair is limited to zero or one attempt")
        self.max_repairs = max_repairs

    def parse(
        self,
        value: Any,
        response_model: type[T],
        *,
        repair: RepairFunction | None = None,
    ) -> T:
        try:
            return validate_structured(value, response_model)
        except Exception as first_error:
            if self.max_repairs == 0 or repair is None:
                raise ProviderError("Provider returned invalid structured output") from first_error
            try:
                repaired = repair(value, first_error)
                return validate_structured(repaired, response_model)
            except Exception as repair_error:
                raise ProviderError("Provider returned invalid structured output after one repair") from repair_error

    # Friendly alias used by provider adapters.
    validate = parse


__all__ = ["StructuredOutputService", "validate_structured"]
