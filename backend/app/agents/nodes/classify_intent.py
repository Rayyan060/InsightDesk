"""Intent classification node.

Contract:
    reads:  message, customer, request
    writes: intent (IntentResult)

Planned: LLM structured-output classification (Ollama) into IntentCategory,
plus deterministic pre-checks (prompt-injection patterns, explicit
"talk to a human" requests). Low confidence maps to IntentCategory.UNCLEAR.
"""

from __future__ import annotations

from app.agents.nodes.base import NodeNotImplementedError, NodeUpdate, audited_node
from app.agents.state import AgentState

NODE_NAME = "classify_intent"


@audited_node(NODE_NAME)
def classify_intent(state: AgentState) -> NodeUpdate:
    raise NodeNotImplementedError(NODE_NAME, "Phase 4")
