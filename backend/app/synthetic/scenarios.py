"""Scenario plan for the synthetic customer dataset.

Division of responsibility (a design decision we can justify to judges):

* **Code owns the invariants.** Which account carries which edge case, the
  exact boundary numbers (usage exactly at a limit, one unit over it, a
  charge on the last day of the refund window, ...), the identifiers (so
  reserved ranges are impossible) and the invoice dates. These must be exact,
  and LLM arithmetic is unreliable (R7).
* **The generator fills in realism.** Company names, owner emails, failure
  reasons, non-pinned usage levels and incident wording come either from a
  seeded RNG (``seeded`` mode) or from the LLM (``llm`` mode). Either way, the
  output is validated against the same schema and checked against this plan.

The reference date anchors every relative edge case. Evaluation requests must
send ``as_of_date`` equal to it (default 2026-10-06, the event date) for the
refund-window boundaries to hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

DEFAULT_SEED = 20261006
DEFAULT_REFERENCE_DATE = date(2026, 10, 6)
DEFAULT_ACCOUNT_COUNT = 36
FIRST_ACCOUNT_NUMBER = 1001
FIRST_INVOICE_NUMBER = 6001

CURRENT_VERSION = "4.3"
PRODUCT_VERSIONS: tuple[str, ...] = ("4.3", "4.2", "4.1", "4.0", "3.9", "3.8")
INR_PER_USD = 83.0

# Required edge cases (guide Section 4.2 plus the Phase 2 brief). Each must be
# carried by at least one account, and is verified from the data itself.
REQUIRED_EDGE_CASES: tuple[str, ...] = (
    "active_within_quota",
    "approaching_quota",
    "workflow_runs_at_limit",
    "workflow_runs_one_over",
    "api_rate_at_limit",
    "api_rate_one_over",
    "failed_payment",
    "suspended_account",
    "duplicate_charge",
    "refund_last_day_of_window",
    "refund_one_day_after_window",
    "no_invoices",
    "multiple_invoices",
    "recently_upgraded",
    "older_product_version",
)


@dataclass(frozen=True)
class AccountSpec:
    """Deterministic plan for one account. ``None`` fields are filled by the generator."""

    scenario: str
    description: str
    plan: str
    status: str
    product_version: str
    currency: str = "USD"
    created_at: date | None = None
    billing_day: int | None = None
    # Pinned usage for the reference period: metric -> exact value or ("ratio", r).
    current_usage: dict[str, object] = field(default_factory=dict)
    # Invoice pattern, interpreted by the generator (see generator._invoice_plan).
    invoice_pattern: str = "monthly"
    months_billed: int | None = None
    cancelled_months_ago: int | None = None
    upgraded_from: str | None = None


# Ordered: account IDs are assigned sequentially from A1001 in this order.
EDGE_CASE_SPECS: tuple[AccountSpec, ...] = (
    AccountSpec("active_within_quota", "Active Pro account comfortably within every limit", "Pro", "active", "4.3",
                current_usage={"workflow_runs": ("ratio", 0.30), "api_calls_peak_per_min": ("ratio", 0.25), "seats_used": ("ratio", 0.5)}),
    AccountSpec("approaching_quota", "Business account at 90% of monthly workflow runs", "Business", "active", "4.3",
                current_usage={"workflow_runs": ("ratio", 0.90)}),
    AccountSpec("workflow_runs_at_limit", "Workflow runs exactly at the Pro monthly limit", "Pro", "active", "4.2",
                current_usage={"workflow_runs": ("ratio", 1.0)}),
    AccountSpec("workflow_runs_one_over", "Workflow runs one unit over the Pro monthly limit", "Pro", "active", "4.3",
                current_usage={"workflow_runs": ("over", 1)}),
    AccountSpec("api_rate_at_limit", "API peak exactly at the Business per-minute limit", "Business", "active", "4.3",
                current_usage={"api_calls_peak_per_min": ("ratio", 1.0)}),
    AccountSpec("api_rate_one_over", "API peak one call over the Pro per-minute limit (429 errors)", "Pro", "active", "4.3",
                current_usage={"api_calls_peak_per_min": ("over", 1)}),
    AccountSpec("seats_at_limit", "Free account using exactly its seat allowance", "Free", "active", "4.3",
                current_usage={"seats_used": ("ratio", 1.0)}),
    AccountSpec("failed_payment", "Latest invoice failed (card declined); account past_due", "Pro", "past_due", "4.3",
                invoice_pattern="latest_failed"),
    AccountSpec("suspended_account", "Two consecutive failed invoices; account suspended", "Business", "suspended", "4.1",
                invoice_pattern="last_two_failed"),
    AccountSpec("duplicate_charge", "Charged twice for the same amount on the same day", "Pro", "active", "4.3",
                billing_day=1, invoice_pattern="duplicate_latest"),
    AccountSpec("refund_last_day_of_window", "Latest paid charge exactly on the last day of the refund window", "Pro", "active", "4.3",
                invoice_pattern="refund_window_last_day"),
    AccountSpec("refund_one_day_after_window", "Latest paid charge one day after the refund window closed", "Business", "active", "4.3",
                invoice_pattern="refund_window_day_after"),
    AccountSpec("refund_enterprise_window", "Enterprise charge 20 days ago: inside the 30-day Enterprise window only", "Enterprise", "active", "4.3",
                invoice_pattern="charged_days_ago:20"),
    AccountSpec("no_invoices", "Free account with no invoices", "Free", "active", "4.3"),
    AccountSpec("multiple_invoices", "Long-standing Enterprise account with six monthly invoices", "Enterprise", "active", "4.3",
                created_at=date(2025, 11, 14), months_billed=6),
    AccountSpec("recently_upgraded", "Upgraded from Pro to Business four days before the reference date", "Business", "active", "4.3",
                billing_day=2, invoice_pattern="upgrade", upgraded_from="Pro"),
    AccountSpec("older_product_version", "Pro account still on legacy CloudFlow 3.9", "Pro", "active", "3.9"),
    AccountSpec("oldest_version_free", "Free account on CloudFlow 3.8", "Free", "active", "3.8"),
    AccountSpec("cancelled_paid_plan", "Pro account cancelled three months ago", "Pro", "cancelled", "4.2",
                cancelled_months_ago=3),
    AccountSpec("cancelled_free", "Cancelled Free account", "Free", "cancelled", "4.0", cancelled_months_ago=2),
    AccountSpec("past_due_enterprise", "Enterprise account past_due after an expired card", "Enterprise", "past_due", "4.2",
                invoice_pattern="latest_failed"),
    AccountSpec("refunded_invoice", "Business account with an earlier invoice already refunded", "Business", "active", "4.2",
                invoice_pattern="older_refunded", months_billed=4),  # needs >= 3 invoices to refund the third-newest
    AccountSpec("inr_billing", "Pro account billed in INR", "Pro", "active", "4.3", currency="INR"),
    AccountSpec("suspended_enterprise", "Enterprise account suspended for non-payment", "Enterprise", "suspended", "4.0",
                invoice_pattern="last_two_failed"),
)

PLATFORM_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("api", "operational"),
    ("workflow-engine", "operational"),
    ("connectors", "degraded"),
    ("billing", "operational"),
    ("webhooks", "outage"),
    ("auth", "operational"),
)
