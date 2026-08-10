"""Static dependency graph for the twelve-agent workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


class AgentNames:
    IP_PREPARATION = "IP Preparation Agent"
    IP_INTELLIGENCE = "IP Intelligence Agent"
    BRAND_INTELLIGENCE = "Brand Intelligence Agent"
    BRAND_COLLABORATION = "Brand Collaboration Agent"
    BRAND_FEATURE = "Brand Feature Agent"
    CREATIVE_BRIEF = "Creative Brief Agent"
    FUSION_DECISION = "Fusion Decision Agent"
    IP_ADAPTATION = "IP Adaptation Agent"
    FUSION_GENERATION = "Fusion Generation Agent"
    IP_GUARDIAN = "IP Guardian Agent"
    RANKING = "Ranking Agent"
    DESIGN_PACKAGE = "Design Package Agent"


AGENT_ORDER: tuple[str, ...] = (
    AgentNames.IP_PREPARATION,
    AgentNames.IP_INTELLIGENCE,
    AgentNames.BRAND_INTELLIGENCE,
    AgentNames.BRAND_COLLABORATION,
    AgentNames.BRAND_FEATURE,
    AgentNames.CREATIVE_BRIEF,
    AgentNames.FUSION_DECISION,
    AgentNames.IP_ADAPTATION,
    AgentNames.FUSION_GENERATION,
    AgentNames.IP_GUARDIAN,
    AgentNames.RANKING,
    AgentNames.DESIGN_PACKAGE,
)


DEFAULT_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    AgentNames.IP_PREPARATION: (),
    AgentNames.IP_INTELLIGENCE: (AgentNames.IP_PREPARATION,),
    AgentNames.BRAND_INTELLIGENCE: (),
    AgentNames.BRAND_COLLABORATION: (AgentNames.BRAND_INTELLIGENCE,),
    AgentNames.BRAND_FEATURE: (
        AgentNames.BRAND_INTELLIGENCE,
        AgentNames.BRAND_COLLABORATION,
    ),
    AgentNames.CREATIVE_BRIEF: (
        AgentNames.IP_INTELLIGENCE,
        AgentNames.BRAND_FEATURE,
    ),
    AgentNames.FUSION_DECISION: (AgentNames.CREATIVE_BRIEF,),
    AgentNames.IP_ADAPTATION: (AgentNames.FUSION_DECISION,),
    AgentNames.FUSION_GENERATION: (AgentNames.IP_ADAPTATION,),
    AgentNames.IP_GUARDIAN: (AgentNames.FUSION_GENERATION,),
    AgentNames.RANKING: (AgentNames.IP_GUARDIAN,),
    AgentNames.DESIGN_PACKAGE: (AgentNames.RANKING,),
}


@dataclass(frozen=True)
class WorkflowGraph:
    """Validated DAG with a deterministic topological presentation order."""

    order: tuple[str, ...] = AGENT_ORDER
    dependencies: Mapping[str, Sequence[str]] = field(
        default_factory=lambda: dict(DEFAULT_DEPENDENCIES)
    )

    def __post_init__(self) -> None:
        nodes = set(self.order)
        if len(nodes) != len(self.order):
            raise ValueError("Workflow order cannot contain duplicate agents")
        if set(self.dependencies) != nodes:
            raise ValueError("Dependency graph nodes must exactly match workflow order")
        for agent, requirements in self.dependencies.items():
            unknown = set(requirements) - nodes
            if unknown:
                raise ValueError(f"{agent} has unknown dependencies: {sorted(unknown)}")
            if agent in requirements:
                raise ValueError(f"{agent} cannot depend on itself")
        self._validate_acyclic()

    def _validate_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(agent: str) -> None:
            if agent in visiting:
                raise ValueError(f"Workflow dependency cycle detected at {agent}")
            if agent in visited:
                return
            visiting.add(agent)
            for dependency in self.dependencies[agent]:
                visit(dependency)
            visiting.remove(agent)
            visited.add(agent)

        for node in self.order:
            visit(node)

    def requirements_for(self, agent_name: str) -> tuple[str, ...]:
        if agent_name not in self.dependencies:
            raise KeyError(f"Unknown workflow agent: {agent_name}")
        return tuple(self.dependencies[agent_name])

    def dependencies_satisfied(self, agent_name: str, completed: Iterable[str]) -> bool:
        return set(self.requirements_for(agent_name)).issubset(set(completed))

    def ready_agents(
        self,
        *,
        completed: Iterable[str],
        pending: Iterable[str] | None = None,
    ) -> list[str]:
        completed_set = set(completed)
        pending_set = set(self.order if pending is None else pending)
        return [
            agent
            for agent in self.order
            if agent in pending_set
            and set(self.requirements_for(agent)).issubset(completed_set)
        ]

    def descendants_of(self, agent_name: str, *, include_self: bool = True) -> tuple[str, ...]:
        """Return downstream nodes in canonical order for checkpoint invalidation."""

        if agent_name not in self.dependencies:
            raise KeyError(f"Unknown workflow agent: {agent_name}")
        affected = {agent_name} if include_self else set()
        frontier = [agent_name]
        while frontier:
            dependency = frontier.pop()
            for candidate, requirements in self.dependencies.items():
                if dependency in requirements and candidate not in affected:
                    affected.add(candidate)
                    frontier.append(candidate)
        return tuple(agent for agent in self.order if agent in affected)
