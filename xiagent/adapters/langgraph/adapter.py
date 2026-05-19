"""Boundary placeholder for a future LangGraph adapter.

XiAgent runtime currently owns deterministic DAG walking and waiting/resume
semantics; this module only marks the adapter boundary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LangGraphAdapter:
    @property
    def engine_name(self) -> str:
        return "langgraph"

    def describe(self) -> dict[str, str]:
        return {
            "engine": self.engine_name,
            "status": "boundary_only",
        }
