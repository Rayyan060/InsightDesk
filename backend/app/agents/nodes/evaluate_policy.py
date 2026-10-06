"""Policy-evaluation node.

Contract:
    reads:  intent, draft_answer, critic_feedback, tool_results, customer
    writes: policy_decision, applied_policy_ids, escalation_reasons, answer_type

Planned: deterministic rules from the policy_registry table (Annex C), such as
refund thresholds, legal/security topics, repeated critic failure or explicit
human request. Rules, not the LLM, decide escalation and refusal.
"""

from __future__ import annotations

from app.agents.nodes.base import NodeNotImplementedError, NodeUpdate, audited_node
from app.agents.state import AgentState

NODE_NAME = "evaluate_policy"


@audited_node(NODE_NAME)
def evaluate_policy(state: AgentState) -> NodeUpdate:
    raise NodeNotImplementedError(NODE_NAME, "Phase 5")
