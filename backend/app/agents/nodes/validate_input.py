"""Input-validation node (implemented in Phase 1: deterministic, no LLM).

Contract:
    reads:  message, request
    writes: input_valid, validation_errors

The API layer already validates the HTTP request. This node re-checks the
invariants the graph depends on, so the graph is safe to invoke from other
entry points (evaluation scripts, tests).
"""

from __future__ import annotations

from app.agents.nodes.base import NodeUpdate, audited_node
from app.agents.state import AgentState
from app.schemas.support import MAX_MESSAGE_CHARS

NODE_NAME = "validate_input"


@audited_node(NODE_NAME)
def validate_input(state: AgentState) -> NodeUpdate:
    errors: list[str] = []
    message = state.get("message")

    if state.get("request") is None:
        errors.append("missing_request_metadata")
    if not isinstance(message, str) or not message.strip():
        errors.append("empty_message")
    elif len(message) > MAX_MESSAGE_CHARS:
        errors.append("message_too_long")
    elif "\x00" in message:
        errors.append("invalid_characters")

    return {"input_valid": not errors, "validation_errors": errors}
