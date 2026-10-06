"""LangGraph foundation: state, routing and wiring (no real agent logic yet)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agents import graph as g
from app.agents.nodes.base import NodeNotImplementedError, audited_node
from app.agents.state import IntentCategory, IntentResult, initial_state
from app.schemas.support import AnswerType, CriticDecision, CriticReport


def _critic(decision: CriticDecision) -> CriticReport:
    return CriticReport(groundedness=0.5, coverage="partial", pii_risk="none", policy_risk="none", decision=decision)


def _state(**extra):
    state = initial_state(trace_id="t" * 32, message="Where is my invoice?", received_at=datetime.now(timezone.utc))
    state.update(extra)
    return state


def test_graph_compiles_with_all_nodes() -> None:
    compiled = g.build_graph()
    assert set(g.DEFAULT_NODES) <= set(compiled.get_graph().nodes)


def test_unknown_node_override_rejected() -> None:
    with pytest.raises(ValueError):
        g.build_graph(node_overrides={"made_up": lambda s: {}})


def test_unimplemented_nodes_fail_loudly_instead_of_faking() -> None:
    compiled = g.build_graph()
    with pytest.raises(NodeNotImplementedError, match="classify_intent"):
        compiled.invoke(_state())


def test_invalid_input_routes_straight_to_audit() -> None:
    assert g.route_after_validation({"input_valid": False}) == g.PERSIST_AUDIT
    assert g.route_after_validation({"input_valid": True}) == g.CLASSIFY_INTENT


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (IntentCategory.KNOWLEDGE, g.RETRIEVE_KNOWLEDGE),
        (IntentCategory.MIXED, g.RETRIEVE_KNOWLEDGE),
        (IntentCategory.ACCOUNT, g.EXECUTE_TOOLS),
        (IntentCategory.UNCLEAR, g.GENERATE_ANSWER),
        (IntentCategory.OUT_OF_SCOPE, g.EVALUATE_POLICY),
        (IntentCategory.UNSAFE, g.EVALUATE_POLICY),
        (IntentCategory.HUMAN_REQUEST, g.EVALUATE_POLICY),
    ],
)
def test_route_after_intent(category, expected) -> None:
    assert g.route_after_intent({"intent": IntentResult(category=category)}) == expected


def test_route_after_intent_requires_intent() -> None:
    with pytest.raises(g.RoutingError):
        g.route_after_intent({})


def test_route_after_critique_respects_revision_cap() -> None:
    revise = [_critic(CriticDecision.REVISE)]
    assert g.route_after_critique({"critic_feedback": revise, "revision_count": 0}, max_revisions=1) == g.GENERATE_ANSWER
    assert g.route_after_critique({"critic_feedback": revise, "revision_count": 1}, max_revisions=1) == g.EVALUATE_POLICY
    answer = [_critic(CriticDecision.ANSWER)]
    assert g.route_after_critique({"critic_feedback": answer, "revision_count": 0}, max_revisions=1) == g.EVALUATE_POLICY
    escalate = [_critic(CriticDecision.ESCALATE)]
    assert g.route_after_critique({"critic_feedback": escalate, "revision_count": 0}, max_revisions=1) == g.EVALUATE_POLICY


def test_r4_default_allows_at_most_one_revision() -> None:
    from app.core.config import load_settings
    from app.core.exceptions import ConfigurationError

    assert load_settings(_env_file=None).max_critic_revisions == 1
    with pytest.raises(ConfigurationError):
        load_settings(_env_file=None, max_critic_revisions=2)


def test_route_after_policy() -> None:
    assert g.route_after_policy({"policy_decision": "escalate"}) == g.ESCALATE
    assert g.route_after_policy({"escalation_reasons": ["refund_over_limit"]}) == g.ESCALATE
    assert g.route_after_policy({"policy_decision": "allow", "escalation_reasons": []}) == g.PERSIST_AUDIT


def test_validate_input_node() -> None:
    from app.agents.nodes import validate_input

    assert validate_input(_state())["input_valid"] is True
    bad = validate_input(_state(message="   "))
    assert bad["input_valid"] is False and bad["validation_errors"] == ["empty_message"]
    assert bad["audit_events"][0].node == "validate_input"


def test_wiring_with_test_doubles_covers_revision_loop_and_escalation() -> None:
    """Test doubles (not production logic) drive the graph through its edges."""

    @audited_node(g.CLASSIFY_INTENT)
    def classify(state):
        return {"intent": IntentResult(category=IntentCategory.MIXED, requires_knowledge=True, requires_tools=True)}

    @audited_node(g.RETRIEVE_KNOWLEDGE)
    def retrieve(state):
        return {"retrieved_documents": []}

    @audited_node(g.EXECUTE_TOOLS)
    def tools(state):
        return {"tool_results": []}

    @audited_node(g.GENERATE_ANSWER)
    def generate(state):
        revising = bool(state.get("critic_feedback"))
        return {
            "draft_answer": "draft",
            "answer_type": AnswerType.ANSWERED,
            "revision_count": state.get("revision_count", 0) + (1 if revising else 0),
        }

    @audited_node(g.SELF_CRITIQUE)
    def critique(state):
        decision = CriticDecision.REVISE if state.get("revision_count", 0) == 0 else CriticDecision.ANSWER
        return {"critic_feedback": [_critic(decision)]}

    @audited_node(g.EVALUATE_POLICY)
    def policy(state):
        return {"policy_decision": "escalate", "escalation_reasons": ["test_rule"]}

    @audited_node(g.ESCALATE)
    def escalate(state):
        return {"answer_type": AnswerType.ESCALATED}

    @audited_node(g.PERSIST_AUDIT)
    def audit(state):
        return {"audit_persisted": True}

    compiled = g.build_graph(
        max_revisions=1,
        node_overrides={
            g.CLASSIFY_INTENT: classify,
            g.RETRIEVE_KNOWLEDGE: retrieve,
            g.EXECUTE_TOOLS: tools,
            g.GENERATE_ANSWER: generate,
            g.SELF_CRITIQUE: critique,
            g.EVALUATE_POLICY: policy,
            g.ESCALATE: escalate,
            g.PERSIST_AUDIT: audit,
        },
    )
    final = compiled.invoke(_state())
    path = [event.node for event in final["audit_events"]]
    assert path == [
        g.VALIDATE_INPUT,
        g.CLASSIFY_INTENT,
        g.RETRIEVE_KNOWLEDGE,
        g.EXECUTE_TOOLS,
        g.GENERATE_ANSWER,
        g.SELF_CRITIQUE,
        g.GENERATE_ANSWER,
        g.SELF_CRITIQUE,
        g.EVALUATE_POLICY,
        g.ESCALATE,
        g.PERSIST_AUDIT,
    ]
    assert final["answer_type"] is AnswerType.ESCALATED
    assert final["escalation_reasons"] == ["test_rule"]
    assert len(final["critic_feedback"]) == 2


def test_persistent_revise_gets_exactly_one_revision_then_policy() -> None:
    """R4: a critic that always says 'revise' gets one revision, then the escalation policy applies."""

    def node(name, update):
        return audited_node(name)(lambda state: update(state))

    overrides = {
        g.CLASSIFY_INTENT: node(g.CLASSIFY_INTENT, lambda s: {"intent": IntentResult(category=IntentCategory.KNOWLEDGE)}),
        g.RETRIEVE_KNOWLEDGE: node(g.RETRIEVE_KNOWLEDGE, lambda s: {"retrieved_documents": []}),
        g.GENERATE_ANSWER: node(
            g.GENERATE_ANSWER,
            lambda s: {"draft_answer": "d", "revision_count": s.get("revision_count", 0) + (1 if s.get("critic_feedback") else 0)},
        ),
        g.SELF_CRITIQUE: node(g.SELF_CRITIQUE, lambda s: {"critic_feedback": [_critic(CriticDecision.REVISE)]}),
        g.EVALUATE_POLICY: node(g.EVALUATE_POLICY, lambda s: {"policy_decision": "escalate", "escalation_reasons": ["low_groundedness"]}),
        g.ESCALATE: node(g.ESCALATE, lambda s: {"answer_type": AnswerType.ESCALATED}),
        g.PERSIST_AUDIT: node(g.PERSIST_AUDIT, lambda s: {"audit_persisted": True}),
    }
    final = g.build_graph(node_overrides=overrides).invoke(_state())
    path = [e.node for e in final["audit_events"]]
    assert path.count(g.GENERATE_ANSWER) == 2 and path.count(g.SELF_CRITIQUE) == 2
    assert final["revision_count"] == 1
