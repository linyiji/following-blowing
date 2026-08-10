"""Agent registry for the AI IP × Brand workflow."""

from __future__ import annotations

from typing import Any

from app.providers.demo_ai import DemoAIProvider
from app.workflow.graph import AgentNames

from .base import BaseAgent
from .brand_collaboration import BrandCollaborationAgent
from .brand_feature import BrandFeatureAgent
from .brand_intelligence import BrandIntelligenceAgent
from .creative_brief import CreativeBriefAgent
from .design_package import DesignPackageAgent
from .fusion_decision import FusionDecisionAgent
from .fusion_generation import FusionGenerationAgent
from .ip_guardian import IPGuardianAgent
from .ip_adaptation import IPAdaptationAgent
from .ip_intelligence import IPIntelligenceAgent
from .ip_preparation import IPPreparationAgent
from .ranking import RankingAgent


def build_default_agents(
    *,
    ai_provider: Any | None = None,
    image_provider: Any | None = None,
    search_provider: Any | None = None,
) -> dict[str, BaseAgent]:
    """Build the standard registry; all agents retain deterministic fallbacks."""

    effective_ai_provider = ai_provider or DemoAIProvider()
    agents: list[BaseAgent] = [
        IPPreparationAgent(),
        IPIntelligenceAgent(ai_provider=effective_ai_provider),
        BrandIntelligenceAgent(ai_provider=effective_ai_provider),
        BrandCollaborationAgent(
            search_provider=search_provider,
            ai_provider=effective_ai_provider,
        ),
        BrandFeatureAgent(ai_provider=effective_ai_provider),
        CreativeBriefAgent(ai_provider=effective_ai_provider),
        FusionDecisionAgent(ai_provider=effective_ai_provider),
        IPAdaptationAgent(ai_provider=effective_ai_provider),
        FusionGenerationAgent(image_provider=image_provider),
        IPGuardianAgent(ai_provider=effective_ai_provider),
        RankingAgent(ai_provider=effective_ai_provider),
        DesignPackageAgent(ai_provider=effective_ai_provider),
    ]
    registry = {agent.name: agent for agent in agents}
    expected = {
        value
        for key, value in vars(AgentNames).items()
        if key.isupper() and isinstance(value, str)
    }
    if set(registry) != expected:
        raise RuntimeError("Default agent registry does not match the workflow graph")
    return registry


__all__ = ["BaseAgent", "build_default_agents"]
