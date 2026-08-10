from __future__ import annotations

from typing import Any

import pytest

from app.agents.base import AgentContext
from app.agents.brand_collaboration import BrandCollaborationAgent
from app.config import ProviderSettings
from app.providers.search_base import SearchResult as ProviderSearchResult
from app.providers.search_mock import MockSearchProvider
from app.providers.search_openai import OpenAIWebSearchProvider
from app.services.errors import SearchError
from app.schemas import (
    BrandProfile,
    CollaborationResearch,
    InputAssets,
    UserIntent,
)
from app.workflow.graph import AgentNames


def _context() -> AgentContext:
    profile = BrandProfile(
        brand_name="Example Brand",
        brand_summary="A sample brand.",
        logo_features=["wordmark"],
        color_palette=["red"],
        product_elements=["package"],
        visual_language=["minimal"],
    )
    return AgentContext(
        run_id="run-search-mode",
        input_assets=InputAssets(ip_image="ip.png", brand_image="brand.png"),
        user_intent=UserIntent(),
        outputs={
            AgentNames.BRAND_INTELLIGENCE: profile.model_dump(mode="json"),
        },
    )


def test_mock_search_is_read_only_demo_and_agent_labels_fixture_research() -> None:
    provider = MockSearchProvider(
        [
            ProviderSearchResult(
                title="Fixture collaboration",
                url="https://example.test/collaboration",
                source="Fixture source",
                summary="Example Brand collaboration archive",
            )
        ]
    )

    assert provider.mode == "demo"
    with pytest.raises(AttributeError):
        provider.mode = "live"  # type: ignore[misc]

    decision = BrandCollaborationAgent(search_provider=provider).process(_context())

    assert decision.output.search_mode == "demo"
    assert decision.output.research_label == "Demo/Mock Research"
    assert len(decision.output.results) == 1
    detail = " ".join(
        [decision.decision_summary, decision.output_summary, *decision.warnings]
    )
    assert "Demo/Mock Research" in detail
    assert "no live web search was performed" in detail


def test_unverified_provider_is_not_called_and_is_explicitly_labeled() -> None:
    class UnverifiedProvider:
        mode = "unverified"

        def __init__(self) -> None:
            self.called = False

        def search(self, query: str, *, limit: int = 5) -> list[Any]:
            del query, limit
            self.called = True
            raise AssertionError("unverified search must not execute")

    provider = UnverifiedProvider()
    decision = BrandCollaborationAgent(search_provider=provider).process(_context())

    assert provider.called is False
    assert decision.output.search_mode == "unverified"
    assert decision.output.research_label == "Unverified Search Capability"
    assert decision.output.evidence_gap is True
    assert "no live web search was performed" in " ".join(decision.warnings)


def test_explicit_verified_provider_records_live_mode_without_network() -> None:
    class FakeLiveProvider:
        mode = "live"

        def search(self, query: str, *, limit: int = 5) -> list[dict[str, str]]:
            assert "Example Brand" in query
            assert limit == 5
            return [
                {
                    "title": "Verified collaboration",
                    "url": "https://example.test/verified",
                    "source": "Official archive",
                    "summary": "A verified historical collaboration.",
                }
            ]

    decision = BrandCollaborationAgent(search_provider=FakeLiveProvider()).process(
        _context()
    )

    assert decision.output.search_mode == "live"
    assert decision.output.research_label == "Live Web Research"
    assert decision.output.evidence_gap is False
    assert "live web search was performed" in decision.output_summary
    assert "no live web search" not in decision.output_summary


def test_openai_search_defaults_unverified_until_explicit_capability_acceptance() -> None:
    settings = ProviderSettings(
        provider="openai",
        model="search-model",
        api_key="test-key",
    )
    unverified = OpenAIWebSearchProvider(settings)
    verified = OpenAIWebSearchProvider(settings, capability_verified=True)

    assert unverified.mode == "unverified"
    assert verified.mode == "live"
    with pytest.raises(SearchError, match="unverified"):
        unverified.search("must not reach the SDK")
    with pytest.raises(AttributeError):
        verified.mode = "demo"  # type: ignore[misc]

    incomplete = OpenAIWebSearchProvider(
        ProviderSettings(provider="openai", model="search-model"),
        capability_verified=True,
    )
    assert incomplete.mode == "unverified"


def test_legacy_collaboration_checkpoint_defaults_to_unverified() -> None:
    value = CollaborationResearch.model_validate(
        {
            "brand_name": "Legacy Brand",
            "query": "legacy query",
            "results": [],
            "patterns": [],
            "evidence_gap": True,
            "warnings": [],
        }
    )

    assert value.search_mode == "unverified"
    assert value.research_label == "Unverified Search Capability"
