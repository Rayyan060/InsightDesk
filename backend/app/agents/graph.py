"""LangGraph wiring for the InsightDesk support workflow.

Topology (see docs/architecture.md for the diagram)::

    START -> validate_input
    validate_input   --valid-->            classify_intent
                     --invalid-->          persist_audit
    classify_intent  --knowledge|mixed-->  retrieve_knowledge
                     --account-->          execute_tools
                     --unclear-->          generate_answer       (clarification)
                     --out_of_scope|unsafe|human_request--> evaluate_policy
    retrieve_knowledge --requires_tools--> execute_tools
                       --otherwise-->      generate_answer
    execute_tools    -> generate_answer
    generate_answer  -> self_critique
    self_critique    --decision=revise and revisions < max (R4: max 1)--> generate_answer
                     --otherwise-->        evaluate_policy
    evaluate_policy  --escalate-->         escalate
                     --otherwise-->        persist_audit
    escalate         -> persist_audit
    persist_audit    -> END

Routing functions are deterministic and depend only on state. All "decisions"
(intent, critic verdict, policy outcome) are produced by nodes, not here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import AgentState, IntentCategory
from app.schemas.support import CriticDecision

# Node names (single source of truth for wiring and tests).
VALIDATE_INPUT = "validate_input"
CLASSIFY_INTENT = "classify_intent"
RETRIEVE_KNOWLEDGE = "retrieve_knowledge"
EXECUTE_TOOLS = "execute_tools"
GENERATE_ANSWER = "generate_answer"
SELF_CRITIQUE = "self_critique"
EVALUATE_POLICY = "evaluate_policy"
ESCALATE = "escalate"
PERSIST_AUDIT = "persist_audit"

DEFAULT_NODES: dict[str, Callable[[AgentState], dict[str, Any]]] = {
    VALIDATE_INPUT: nodes.validate_input,
    CLASSIFY_INTENT: nodes.classify_intent,
    RETRIEVE_KNOWLEDGE: nodes.retrieve_knowledge,
    EXECUTE_TOOLS: nodes.execute_tools,
    GENERATE_ANSWER: nodes.generate_answer,
    SELF_CRITIQUE: nodes.self_critique,
    EVALUATE_POLICY: nodes.evaluate_policy,
    ESCALATE: nodes.escalate,
    PERSIST_AUDIT: nodes.persist_audit,
}


class RoutingError(RuntimeError):
    """State is missing data a routing function requires (a node contract bug)."""


# ---------------------------------------------------------------------- #
# Routing functions
# ---------------------------------------------------------------------- #
def route_after_validation(state: AgentState) -> str:
    return CLASSIFY_INTENT if state.get("input_valid") else PERSIST_AUDIT


def route_after_intent(state: AgentState) -> str:
    intent = state.get("intent")
    if intent is None:
        raise RoutingError("classify_intent did not set 'intent'.")
    category = intent.category
    if category in (IntentCategory.OUT_OF_SCOPE, IntentCategory.UNSAFE, IntentCategory.HUMAN_REQUEST):
        return EVALUATE_POLICY
    if category is IntentCategory.UNCLEAR:
        return GENERATE_ANSWER
    if category is IntentCategory.ACCOUNT:
        return EXECUTE_TOOLS
    return RETRIEVE_KNOWLEDGE  # KNOWLEDGE or MIXED


def route_after_retrieval(state: AgentState) -> str:
    intent = state.get("intent")
    if intent is not None and intent.requires_tools:
        return EXECUTE_TOOLS
    return GENERATE_ANSWER


def route_after_critique(state: AgentState, *, max_revisions: int) -> str:
    feedback = state.get("critic_feedback") or []
    if not feedback:
        raise RoutingError("self_critique did not append critic feedback.")
    wants_revision = feedback[-1].decision is CriticDecision.REVISE
    if wants_revision and state.get("revision_count", 0) < max_revisions:
        return GENERATE_ANSWER
    return EVALUATE_POLICY


def route_after_policy(state: AgentState) -> str:
    if state.get("policy_decision") == "escalate" or state.get("escalation_reasons"):
        return ESCALATE
    return PERSIST_AUDIT


# ---------------------------------------------------------------------- #
# Graph construction
# ---------------------------------------------------------------------- #
def build_graph(
    *,
    max_revisions: int = 1,
    node_overrides: Mapping[str, Callable[[AgentState], dict[str, Any]]] | None = None,
) -> Any:
    """Build and compile the workflow.

    ``node_overrides`` lets tests and later phases swap individual nodes
    without touching the wiring.
    """
    node_impls = {**DEFAULT_NODES, **(node_overrides or {})}
    unknown = set(node_impls) - set(DEFAULT_NODES)
    if unknown:
        raise ValueError(f"Unknown node names: {sorted(unknown)}")

    graph = StateGraph(AgentState)
    for name, fn in node_impls.items():
        graph.add_node(name, fn)

    graph.add_edge(START, VALIDATE_INPUT)
    graph.add_conditional_edges(
        VALIDATE_INPUT, route_after_validation, [CLASSIFY_INTENT, PERSIST_AUDIT]
    )
    graph.add_conditional_edges(
        CLASSIFY_INTENT,
        route_after_intent,
        [RETRIEVE_KNOWLEDGE, EXECUTE_TOOLS, GENERATE_ANSWER, EVALUATE_POLICY],
    )
    graph.add_conditional_edges(
        RETRIEVE_KNOWLEDGE, route_after_retrieval, [EXECUTE_TOOLS, GENERATE_ANSWER]
    )
    graph.add_edge(EXECUTE_TOOLS, GENERATE_ANSWER)
    graph.add_edge(GENERATE_ANSWER, SELF_CRITIQUE)
    graph.add_conditional_edges(
        SELF_CRITIQUE,
        partial(route_after_critique, max_revisions=max_revisions),
        [GENERATE_ANSWER, EVALUATE_POLICY],
    )
    graph.add_conditional_edges(EVALUATE_POLICY, route_after_policy, [ESCALATE, PERSIST_AUDIT])
    graph.add_edge(ESCALATE, PERSIST_AUDIT)
    graph.add_edge(PERSIST_AUDIT, END)

    return graph.compile()
