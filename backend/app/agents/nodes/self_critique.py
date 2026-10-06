"""Self-critique node.

Contract:
    reads:  draft_answer, citations, retrieved_documents, tool_results
    writes: critic_feedback (appended CriticReport)

Planned: check groundedness, citation coverage, policy compliance and tone.
Verdict 'revise' loops back to generate_answer until
settings.max_critic_revisions (R4: at most one) is reached.
"""

from __future__ import annotations

from app.agents.nodes.base import NodeNotImplementedError, NodeUpdate, audited_node
from app.agents.state import AgentState

NODE_NAME = "self_critique"


@audited_node(NODE_NAME)
def self_critique(state: AgentState) -> NodeUpdate:
    raise NodeNotImplementedError(NODE_NAME, "Phase 4")
