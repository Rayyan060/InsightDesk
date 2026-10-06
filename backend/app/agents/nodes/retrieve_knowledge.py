"""Knowledge retrieval node.

Contract:
    reads:  message, intent, request.as_of_date
    writes: retrieved_documents, conflicts_detected

Planned: ChromaDB similarity search (sentence-transformers embeddings),
filtered by effective_date <= as_of_date, then version precedence
(app.rag.precedence) to mark superseded chunks and record conflicts.
"""

from __future__ import annotations

from app.agents.nodes.base import NodeNotImplementedError, NodeUpdate, audited_node
from app.agents.state import AgentState

NODE_NAME = "retrieve_knowledge"


@audited_node(NODE_NAME)
def retrieve_knowledge(state: AgentState) -> NodeUpdate:
    raise NodeNotImplementedError(NODE_NAME, "Phase 3")
