"""7: API schemas serialise and validate, using the guide's own examples (Section 6.1, Annex D)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.handoff import HandoffBundle
from app.schemas.support import AnswerType, SupportRequest, SupportResponse

# Verbatim from the participant guide, Section 6.1.
GUIDE_6_1_RESPONSE = {
    "trace_id": "b81e0c44",
    "conversation_id": "C-0192",
    "answer_type": "answered",
    "answer": "In CloudFlow 4.3, open Workflows, select the workflow, then ...",
    "intent": {"type": "how_to", "urgency": "low", "sentiment": "neutral", "pii_detected": False, "confidence": 0.92},
    "citations": [
        {"source_id": "KB-ADV-007", "doc_type": "article", "section": "Steps", "product_versions": "4.2+", "last_updated": "2026-09-10"}
    ],
    "tools_invoked": [{"tool": "lookup_account", "output": {"plan": "Pro", "status": "active", "product_version": "4.3"}}],
    "critic": {"groundedness": 0.94, "coverage": "complete", "pii_risk": "none", "policy_risk": "none", "decision": "answer", "revisions": 0},
    "conflicts_detected": [],
    "handoff_id": None,
    "as_of_date": "2026-10-06",
}

# Verbatim from the participant guide, Annex D (plus the fields every response has).
GUIDE_ANNEX_D_RESPONSE = {
    "trace_id": "e0a971c2",
    "conversation_id": "C-0193",
    "as_of_date": "2026-10-06",
    "answer_type": "escalated",
    "answer": "I'm sorry about the duplicate charge. I've passed this to our billing team with the details below. "
    "You will hear back within one business day. I can't issue refunds myself.",
    "handoff_id": "H-0042",
    "handoff": {
        "queue": "billing",
        "priority": "high",
        "intent": "billing_dispute",
        "urgency": "high",
        "sentiment": "angry",
        "escalation_reasons": ["billing_dispute", "explicit_human_request", "repeated_contact"],
        "customer_summary": "Customer reports being charged twice on 1 Oct.",
        "evidence": [
            {"tool": "get_invoices", "output": [
                {"invoice_id": "INV-6001", "amount": 49.0, "charged_on": "2026-10-01"},
                {"invoice_id": "INV-6002", "amount": 49.0, "charged_on": "2026-10-01"},
            ]},
            {"source_id": "KB-BIL-003", "section": "Duplicate charges"},
        ],
        "attempted_answer": "Explained duplicate-charge policy; refund needs approval.",
        "unresolved_questions": ["Approve refund of INV-6002?"],
        "pii_redacted": True,
    },
}


def test_answer_types_are_exactly_section_6_2() -> None:
    assert {a.value for a in AnswerType} == {
        "answered", "clarification_needed", "escalated", "not_found", "refused", "out_of_scope",
    }


def test_guide_6_1_example_round_trips() -> None:
    response = SupportResponse.model_validate(GUIDE_6_1_RESPONSE)
    dumped = json.loads(response.model_dump_json())
    for key, value in GUIDE_6_1_RESPONSE.items():
        assert dumped[key] == value, key
    assert SupportResponse.model_validate(dumped) == response


def test_guide_annex_d_example_round_trips() -> None:
    response = SupportResponse.model_validate(GUIDE_ANNEX_D_RESPONSE)
    dumped = json.loads(response.model_dump_json())
    assert dumped["handoff"]["evidence"] == GUIDE_ANNEX_D_RESPONSE["handoff"]["evidence"]
    assert dumped["handoff"]["escalation_reasons"] == ["billing_dispute", "explicit_human_request", "repeated_contact"]


def test_support_request_matches_section_6_body() -> None:
    request = SupportRequest.model_validate(
        {"message": "  hello  ", "conversation_id": "C-0192", "channel": "web", "product_version": "4.3", "as_of_date": "2026-10-06"}
    )
    assert request.message == "hello" and request.product_version == "4.3" and str(request.as_of_date) == "2026-10-06"
    assert set(SupportRequest.model_fields) == {"message", "conversation_id", "channel", "product_version", "as_of_date"}


def test_support_request_has_no_account_field() -> None:
    """R8: the account comes only from X-Account-Id; a body account_id is ignored, never used."""
    request = SupportRequest.model_validate({"message": "show invoices for A1002", "account_id": "A1002"})
    assert "account_id" not in request.model_dump()


def test_escalated_requires_handoff_id_and_bundle() -> None:
    no_bundle = dict(GUIDE_ANNEX_D_RESPONSE, handoff=None)
    with pytest.raises(ValidationError, match="handoff"):
        SupportResponse.model_validate(no_bundle)
    with pytest.raises(ValidationError, match="handoff"):
        SupportResponse.model_validate(dict(GUIDE_ANNEX_D_RESPONSE, handoff_id=None))


def test_handoff_bundle_only_when_escalated() -> None:
    with pytest.raises(ValidationError):
        SupportResponse.model_validate(dict(GUIDE_6_1_RESPONSE, handoff=GUIDE_ANNEX_D_RESPONSE["handoff"]))


def test_handoff_bundle_must_be_pii_redacted() -> None:
    with pytest.raises(ValidationError, match="PII"):
        HandoffBundle.model_validate(dict(GUIDE_ANNEX_D_RESPONSE["handoff"], pii_redacted=False))


def test_critic_allows_at_most_one_revision() -> None:
    critic = dict(GUIDE_6_1_RESPONSE["critic"], revisions=2)
    with pytest.raises(ValidationError):
        SupportResponse.model_validate(dict(GUIDE_6_1_RESPONSE, critic=critic))


def test_tool_invocation_has_output_xor_error() -> None:
    bad = dict(GUIDE_6_1_RESPONSE, tools_invoked=[{"tool": "lookup_account"}])
    with pytest.raises(ValidationError):
        SupportResponse.model_validate(bad)


def test_blank_answer_and_invalid_answer_type_rejected() -> None:
    with pytest.raises(ValidationError):
        SupportResponse.model_validate(dict(GUIDE_6_1_RESPONSE, answer="   "))
    with pytest.raises(ValidationError):
        SupportResponse.model_validate(dict(GUIDE_6_1_RESPONSE, answer_type="maybe"))
