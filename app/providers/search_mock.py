from __future__ import annotations

from typing import Iterable, Mapping, Any

from .search_base import SearchProvider, SearchResult


class MockSearchProvider(SearchProvider):
    """Deterministic fixture search; results are explicitly marked as demo."""

    def __init__(self, results: Iterable[SearchResult | Mapping[str, Any]] | None = None) -> None:
        self.results = [SearchResult.from_value(item) for item in (results or [])]

    @property
    def mode(self) -> str:
        return "demo"

    def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        words = {word.lower() for word in query.split() if word}
        if not words:
            return self.results[:limit]
        matched = [
            item
            for item in self.results
            if any(word in f"{item.title} {item.summary}".lower() for word in words)
        ]
        return (matched or self.results)[:limit]


# Requirement-compatible alias.
DemoSearchProvider = MockSearchProvider


__all__ = ["DemoSearchProvider", "MockSearchProvider"]
