"""Answer-generation node.

Contract:
    reads:  message, intent, retrieved_documents, tool_results, critic_feedback
    writes: draft_answer, answer_type, citations, revision_count
            (incremented when this call is a revision requested by the critic)

Planned: grounded generation via Ollama using only retrieved chunks and tool
results; every factual claim must map to a citation. On revision, the latest
critic issues are included in the prompt.
"""

from __future__ import annotations

from app.agents.nodes.base import NodeNotImplementedError, NodeUpdate, audited_node
from app.agents.state import AgentState

NODE_NAME = "generate_answer"


@audited_node(NODE_NAME)
def generate_answer(state: AgentState) -> NodeUpdate:
    raise NodeNotImplementedError(NODE_NAME, "Phase 4")
