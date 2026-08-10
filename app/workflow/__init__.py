"""Deterministic, checkpoint-aware workflow orchestration.

The engine is imported lazily so individual agent modules can use the graph
constants without creating an agents ↔ engine import cycle.
"""

from .graph import AGENT_ORDER, AgentNames, WorkflowGraph

MAX_GUARDIAN_RETRIES = 2

__all__ = [
    "AGENT_ORDER",
    "MAX_GUARDIAN_RETRIES",
    "AgentNames",
    "WorkflowEngine",
    "WorkflowGraph",
]


def __getattr__(name: str):
    if name == "WorkflowEngine":
        from .engine import WorkflowEngine

        return WorkflowEngine
    raise AttributeError(name)
