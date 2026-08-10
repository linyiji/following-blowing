from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    source: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def model_dump(self, **kwargs: Any) -> dict[str, str]:
        """Pydantic-compatible bridge for workflow schemas."""

        del kwargs
        return self.to_dict()

    @classmethod
    def from_value(cls, value: "SearchResult | Mapping[str, Any]") -> "SearchResult":
        if isinstance(value, cls):
            return value
        return cls(
            title=str(value.get("title", "")),
            url=str(value.get("url", "")),
            source=str(value.get("source", "")),
            summary=str(value.get("summary", "")),
        )


class SearchProvider(ABC):
    @property
    def mode(self) -> str:
        """Return the audited provider mode without exposing mutable state.

        Third-party providers that have not declared and verified a capability
        inherit the safe ``unverified`` mode.  Concrete providers may override
        this read-only property with ``demo`` or ``live``.
        """

        return "unverified"

    @abstractmethod
    def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        raise NotImplementedError


__all__ = ["SearchProvider", "SearchResult"]
