"""Research verified historical collaboration evidence through SearchProvider."""

from __future__ import annotations

from typing import Any

from app.errors import SearchError
from app.schemas import (
    BrandProfile,
    CollaborationResearch,
    CollaborationResearchReasoning,
    SearchResult,
)
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


def _search_result(value: Any) -> SearchResult:
    if isinstance(value, SearchResult):
        return value
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return SearchResult.model_validate(value)


_RESEARCH_LABELS = {
    "demo": "Demo/Mock Research",
    "live": "Live Web Research",
    "unverified": "Unverified Search Capability",
}


def _search_mode(provider: Any | None) -> str:
    if provider is None:
        return "unverified"
    mode = str(getattr(provider, "mode", "unverified")).strip().lower()
    return mode if mode in _RESEARCH_LABELS else "unverified"


class BrandCollaborationAgent(BaseAgent[CollaborationResearch]):
    name = AgentNames.BRAND_COLLABORATION
    prompt_id = "brand_collaboration"
    responsibility = "Find sourced brand collaboration precedents without inventing cases."
    handoff = "Sourced collaboration patterns → Brand Feature Agent"

    def __init__(
        self,
        *,
        search_provider: Any | None = None,
        ai_provider: Any | None = None,
    ) -> None:
        super().__init__(ai_provider=ai_provider)
        self.search_provider = search_provider

    def input_summary(self, context: AgentContext) -> str:
        profile = context.require_output(AgentNames.BRAND_INTELLIGENCE, BrandProfile)
        label = _RESEARCH_LABELS[_search_mode(self.search_provider)]
        return f"{label} for historical collaborations involving {profile.brand_name}."

    def process(self, context: AgentContext) -> AgentDecision[CollaborationResearch]:
        profile = context.require_output(AgentNames.BRAND_INTELLIGENCE, BrandProfile)
        query = f"{profile.brand_name} official collaboration design history"
        results: list[SearchResult] = []
        warnings: list[str] = []
        search_mode = _search_mode(self.search_provider)
        research_label = _RESEARCH_LABELS[search_mode]
        if search_mode == "unverified":
            warnings.append(
                "Search capability is unverified; no live web search was performed."
            )
        elif self.search_provider is not None:
            try:
                raw_results = self.search_provider.search(query, limit=5)
                results = [_search_result(result) for result in raw_results]
            except SearchError:
                raise
            except Exception as exc:
                raise SearchError(
                    "Brand collaboration search failed",
                    context={"provider_type": type(self.search_provider).__name__},
                ) from exc
        if search_mode == "demo":
            warnings.append(
                "Demo/Mock Research uses fixture data; no live web search was performed."
            )

        demo_reasoning = CollaborationResearchReasoning(
            patterns=(
                ["Use only recurring patterns supported by the returned sources"]
                if results
                else ["Do not award historical-reference credit without sourced evidence"]
            ),
            rationale=(
                "Patterns are limited to the supplied result summaries."
                if results
                else "No sourced precedent exists, so the evidence gap remains explicit."
            ),
            evidence_used=[result.url for result in results],
            evidence_gap=not bool(results),
        )
        reasoning = (
            self.ai_provider.generate_structured(
                prompt=self.prompt_text,
                response_model=CollaborationResearchReasoning,
                context={
                    "brand_profile": profile.model_dump(mode="json"),
                    "search_mode": search_mode,
                    "search_results": [result.model_dump(mode="json") for result in results],
                },
                model_role="main",
                demo_output=demo_reasoning.model_dump(mode="json"),
            )
            if self.ai_provider is not None
            else demo_reasoning
        )
        if not isinstance(reasoning, CollaborationResearchReasoning):
            reasoning = CollaborationResearchReasoning.model_validate(reasoning)
        output = CollaborationResearch(
            brand_name=profile.brand_name,
            query=query,
            results=results,
            patterns=reasoning.patterns,
            evidence_gap=not bool(results),
            warnings=warnings,
            search_mode=search_mode,
            research_label=research_label,
        )
        evidence = tuple(
            [
                *(f"{result.title} — {result.source} ({result.url})" for result in results),
                reasoning.rationale,
            ]
        )
        return AgentDecision(
            output=output,
            decision_summary=(
                f"{research_label}: retained {len(results)} collaboration reference(s)."
                if results
                else f"{research_label}: recorded an evidence gap instead of fabricating history."
            ),
            output_summary=(
                f"{research_label} contains {len(results)} result(s); "
                + (
                    "live web search was performed."
                    if search_mode == "live"
                    else "no live web search was performed."
                )
            ),
            evidence=evidence,
            warnings=tuple(warnings),
        )
