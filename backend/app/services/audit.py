"""Audit persistence (Phase 5).

Planned: persist one audit record per support turn keyed by trace_id (intent,
nodes executed with timings, tools invoked, citations, critic verdicts, policy
decisions, handoff ID). Values pass through app.core.security.redact before
storage unless a field is explicitly required for review.
"""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState
from app.core.exceptions import NotImplementedFeatureError


class AuditService:
    def record_turn(self, state: AgentState) -> None:
        raise NotImplementedFeatureError("Audit persistence", planned_phase="Phase 5")

    def get_trail(self, trace_id: str) -> dict[str, Any]:
        raise NotImplementedFeatureError("Audit retrieval", planned_phase="Phase 5")
