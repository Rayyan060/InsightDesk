"""Deterministic tool-execution node.

Contract:
    reads:  intent.requested_tools, customer (validated account context)
    writes: tool_results, tools_invoked

Planned: dispatch to app.tools.* with the AccountContext from the request.
The account ID is NEVER taken from the message text or model output. Missing
account context leads to a clarification, not a guess.
"""

from __future__ import annotations

from app.agents.nodes.base import NodeNotImplementedError, NodeUpdate, audited_node
from app.agents.state import AgentState

NODE_NAME = "execute_tools"


@audited_node(NODE_NAME)
def execute_tools(state: AgentState) -> NodeUpdate:
    raise NodeNotImplementedError(NODE_NAME, "Phase 4")
