"""Policy engine (Phase 5).

Planned: load rules from the policy_registry table (Annex C) and evaluate them
deterministically against agent state to decide allow / refuse / escalate.
Rules carry IDs so every decision is attributable in the audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.agents.state import AgentState
from app.core.exceptions import NotImplementedFeatureError

PolicyOutcome = Literal["allow", "refuse", "escalate"]


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    policy_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


class PolicyService:
    def evaluate(self, state: AgentState) -> PolicyDecision:
        raise NotImplementedFeatureError("Policy evaluation", planned_phase="Phase 5")
