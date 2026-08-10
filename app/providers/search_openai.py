from __future__ import annotations

import json
from typing import Any, Mapping

from app.config import ProviderSettings
from app.services.errors import SearchError

from .client import ProviderClient
from .search_base import SearchProvider, SearchResult


class OpenAIWebSearchProvider(SearchProvider):
    def __init__(
        self,
        settings: ProviderSettings,
        *,
        client: ProviderClient | None = None,
        capability_verified: bool = False,
    ) -> None:
        self.settings = settings
        self.provider_client = client or ProviderClient(timeout=settings.timeout)
        self._capability_verified = bool(capability_verified)
        self._sdk_client: Any | None = None

    @property
    def mode(self) -> str:
        """Report live only after both configuration and capability verification."""

        return (
            "live"
            if (
                self._capability_verified
                and not self.settings.is_demo
                and self.settings.configured
            )
            else "unverified"
        )

    @property
    def capability_verified(self) -> bool:
        return self._capability_verified

    def _require_sdk(self) -> Any:
        if not self.settings.api_key or not self.settings.model:
            raise SearchError("OpenAI web search provider is not configured")
        if self._sdk_client is None:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError as exc:
                raise SearchError("OpenAI SDK is not installed") from exc
            self._sdk_client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=self.settings.timeout,
            )
        return self._sdk_client

    def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        if not query.strip():
            return []
        if limit <= 0:
            return []
        if self.mode != "live":
            raise SearchError(
                "OpenAI web search capability is unverified; live search was not executed",
                context={"search_mode": "unverified"},
            )
        sdk = self._require_sdk()
        prompt = (
            "Search the web for verifiable sources answering the query below. "
            f"Return at most {limit} results as a JSON array. Every item must have "
            "title, url, source, and summary. Do not invent sources.\n\n"
            f"Query: {query}"
        )

        def request() -> Any:
            return sdk.responses.create(
                model=self.settings.model,
                tools=[{"type": "web_search"}],
                input=prompt,
            )

        response = self.provider_client.execute("search.web", request)
        raw = getattr(response, "output_text", "")
        try:
            values = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise SearchError("Search provider returned invalid structured output") from exc
        if not isinstance(values, list):
            raise SearchError("Search provider returned a non-list result")
        results: list[SearchResult] = []
        for value in values[:limit]:
            if not isinstance(value, Mapping):
                continue
            result = SearchResult.from_value(value)
            if result.title and result.url.startswith("https://") and result.summary:
                results.append(result)
        return results


__all__ = ["OpenAIWebSearchProvider"]
