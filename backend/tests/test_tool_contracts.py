"""Contracts of the eight required tools (Annex C): names, scoping, errors, no fabricated output."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.core.security import AccountContext
from app.database.annex_c import ANNEX_C_SCHEMA
from app.schemas.tools import (
    PasswordResetResult,
    RefundEligibilityResult,
    ToolErrorCode,
    ToolName,
    ToolStatus,
)
from app.tools.base import ToolContext, ToolFailure
from app.tools.registry import TOOL_SPECS, invoke_tool, to_invocation

ANNEX_C_TOOLS = {
    "lookup_account", "get_usage", "get_plan_limits", "get_invoices",
    "check_refund_eligibility", "check_platform_status", "send_password_reset", "create_handoff",
}
VALID_ARGS = {
    "lookup_account": {},
    "get_usage": {"period": "2026-10"},
    "get_plan_limits": {"plan": "Pro"},
    "get_invoices": {"limit": 5, "status": "paid"},
    "check_refund_eligibility": {"invoice_id": "INV-6040"},
    "check_platform_status": {"component": "connectors"},
    "send_password_reset": {},
    "create_handoff": {
        "conversation_id": "C-0001", "queue": "billing", "priority": "high",
        "bundle": {
            "queue": "billing", "priority": "high", "intent": "billing_dispute", "urgency": "high", "sentiment": "angry",
            "escalation_reasons": ["billing_dispute"], "customer_summary": "Charged twice.", "evidence": [],
            "pii_redacted": True,
        },
    },
}


@pytest.fixture
def ctx(db):
    with db.session_scope() as session:
        yield ToolContext(session=session, as_of_date=date(2026, 10, 6), trace_id="t" * 32, account=AccountContext(account_id="A1001"))


@pytest.fixture
def anonymous_ctx(db):
    with db.session_scope() as session:
        yield ToolContext(session=session, as_of_date=date(2026, 10, 6), trace_id="t" * 32, account=None)


def test_exactly_the_annex_c_tools_are_registered() -> None:
    assert {t.value for t in ToolName} == ANNEX_C_TOOLS == {s.name.value for s in TOOL_SPECS.values()}


@pytest.mark.parametrize("name", sorted(ANNEX_C_TOOLS))
def test_request_models_never_carry_an_account_id(name) -> None:
    spec = TOOL_SPECS[ToolName(name)]
    assert "account_id" not in spec.request_model.model_fields
    assert spec.request_model.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("name", sorted(ANNEX_C_TOOLS))
def test_llm_supplied_account_id_is_rejected(ctx, name) -> None:
    result = invoke_tool(name, ctx, {**VALID_ARGS[name], "account_id": "A1002"})
    assert result.status is ToolStatus.ERROR and result.error.code is ToolErrorCode.INVALID_ARGUMENTS
    assert result.output is None


@pytest.mark.parametrize("name", sorted(n for n in ANNEX_C_TOOLS if TOOL_SPECS[ToolName(n)].account_scoped))
def test_account_scoped_tools_require_header_context(anonymous_ctx, name) -> None:
    result = invoke_tool(name, anonymous_ctx, VALID_ARGS[name])
    assert result.error.code is ToolErrorCode.ACCOUNT_CONTEXT_REQUIRED


@pytest.mark.parametrize("name", sorted(ANNEX_C_TOOLS))
def test_unimplemented_tools_never_fabricate_output(ctx, name) -> None:
    result = invoke_tool(name, ctx, VALID_ARGS[name])
    assert result.status is ToolStatus.ERROR
    assert result.error.code is ToolErrorCode.NOT_IMPLEMENTED and "Phase 5" in result.error.message
    assert result.output is None
    assert to_invocation(result).model_dump() == {"tool": name, "error": result.error.model_dump()}


def test_unknown_tool_and_invalid_arguments(ctx) -> None:
    assert invoke_tool("issue_refund", ctx, {}).error.code is ToolErrorCode.UNKNOWN_TOOL
    assert invoke_tool("get_usage", ctx, {"period": "October"}).error.code is ToolErrorCode.INVALID_ARGUMENTS
    assert invoke_tool("get_invoices", ctx, {"limit": 500}).error.code is ToolErrorCode.INVALID_ARGUMENTS


def test_tool_database_dependencies_are_annex_c_tables() -> None:
    for spec in TOOL_SPECS.values():
        assert set(spec.reads) <= set(ANNEX_C_SCHEMA), spec.name
    writers = {spec.name.value: spec.writes for spec in TOOL_SPECS.values() if spec.writes}
    assert writers == {"create_handoff": ("handoffs",)}  # nothing else writes; refunds are never executed


def test_password_reset_result_can_never_carry_a_link_or_token() -> None:
    assert not {"token", "link", "url", "reset_link"} & set(PasswordResetResult.model_fields)
    ok = PasswordResetResult(status="reset_email_sent", sent_to="n***@example.com", message="A reset email was sent to the address on file.")
    assert ok.status == "reset_email_sent"
    for leak in ("Use https://cloudflow.example.com/reset?t=abc", "Your code is 8f9a7c6b5d4e3f2a1b0c9d8e7f6a"):
        with pytest.raises(ValidationError):
            PasswordResetResult(status="reset_email_sent", sent_to="n***@example.com", message=leak)
    with pytest.raises(ValidationError):
        PasswordResetResult(status="reset_email_sent", sent_to="n***@example.com", message="ok", token="abc")


def test_refund_result_always_requires_a_human() -> None:
    base = dict(invoice_id="INV-6040", eligible=True, reasons=["within window"], as_of_date="2026-10-06",
                days_since_charge=14, refund_window_days=14, policy_rule_ids=["REFUND-WINDOW-01"])
    assert RefundEligibilityResult(**base).requires_human_approval is True
    with pytest.raises(ValidationError):
        RefundEligibilityResult(**base, requires_human_approval=False)


def test_tool_context_scoping(anonymous_ctx, ctx) -> None:
    with pytest.raises(ToolFailure) as excinfo:
        anonymous_ctx.scoped()
    assert excinfo.value.code is ToolErrorCode.ACCOUNT_CONTEXT_REQUIRED
    assert ctx.scoped().account_id == "A1001"
