"""Audit-persistence node (terminal).

Contract:
    reads:  entire state (redacted)
    writes: audit_persisted

Planned: persist audit_events, intent, tools invoked, citations, critic verdicts
and policy decisions keyed by trace_id via app.services.audit. Raw message text
is stored only if retention policy allows; it is never logged.
"""

from __future__ import annotations

from app.agents.nodes.base import NodeNotImplementedError, NodeUpdate, audited_node
from app.agents.state import AgentState

NODE_NAME = "persist_audit"


@audited_node(NODE_NAME)
def persist_audit(state: AgentState) -> NodeUpdate:
    raise NodeNotImplementedError(NODE_NAME, "Phase 5")
