"""Escalation / human-handoff node.

Contract:
    reads:  escalation_reasons, request, customer, draft_answer
    writes: handoff (HandoffInfo with handoff_id), answer_type=escalated

Planned: create a row in the handoffs table (Annex C) via app.tools.handoff and
produce a customer-facing escalation message.
"""

from __future__ import annotations

from app.agents.nodes.base import NodeNotImplementedError, NodeUpdate, audited_node
from app.agents.state import AgentState

NODE_NAME = "escalate"


@audited_node(NODE_NAME)
def escalate(state: AgentState) -> NodeUpdate:
    raise NodeNotImplementedError(NODE_NAME, "Phase 5")
