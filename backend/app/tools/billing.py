"""get_invoices and check_refund_eligibility (tables: invoices, accounts, policy_registry)."""

from __future__ import annotations

from app.core.exceptions import NotImplementedFeatureError
from app.schemas.tools import CheckRefundEligibilityRequest, GetInvoicesRequest, InvoiceList, RefundEligibilityResult
from app.tools.base import ToolContext


def get_invoices(ctx: ToolContext, request: GetInvoicesRequest) -> InvoiceList:
    raise NotImplementedFeatureError("Tool get_invoices", planned_phase="Phase 5")


def check_refund_eligibility(ctx: ToolContext, request: CheckRefundEligibilityRequest) -> RefundEligibilityResult:
    """Deterministic eligibility from the policy registry, as of ``ctx.as_of_date``.

    Rules: REFUND-WINDOW-* (by plan and effective date; the last day of the
    window is eligible), REFUND-STATUS-01 (only paid invoices) and
    REFUND-APPROVAL-01 (always requires a human). Never issues a refund.
    """
    raise NotImplementedFeatureError("Tool check_refund_eligibility", planned_phase="Phase 5")
