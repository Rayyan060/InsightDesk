"""ORM models for the mandatory Annex C tables.

Source of truth: Annex C, "Fixed data schema (SQLite)", of the participant guide
(docs/reference/participant_guide.pdf; transcription in
docs/reference/guide_extract.md).

Rules followed here:

* Column names and SQL types (TEXT / INTEGER / REAL) are exactly as Annex C
  lists them. Nothing has been renamed or removed. Dates and timestamps stay
  TEXT, as specified.
* Primary keys and foreign keys are exactly those Annex C marks (PK, FK).
* CHECK constraints encode only rules that Annex C states explicitly:
  enumerations, `amount > 0`, the account ID format, "last four digits only",
  "@example.com only", "empty unless failed" and "empty if operational".
  Cross-row business rules (for example, statuses consistent with invoices)
  live in ``app.database.validation``. They are reported, not enforced by the
  database, so judge data is never blocked by our own interpretation.
* Optional columns are the ones Annex C describes as possibly empty
  (`failure_reason`, `incident_id`), the ones it doesn't require
  (`card_last4`, `source_section`), and `handoffs.conversation_id` and
  `handoffs.account_id`, since a handoff may be raised without an account.
* Indexes are additive and don't change the schema contract.
"""

from __future__ import annotations

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

# --- Annex C enumerations --------------------------------------------------
PLANS: tuple[str, ...] = ("Free", "Pro", "Business", "Enterprise")
ACCOUNT_STATUSES: tuple[str, ...] = ("active", "past_due", "suspended", "cancelled")
INVOICE_STATUSES: tuple[str, ...] = ("paid", "failed", "refunded")
PLATFORM_STATUSES: tuple[str, ...] = ("operational", "degraded", "outage")
HANDOFF_PRIORITIES: tuple[str, ...] = ("low", "normal", "high", "urgent")

# Reserved for judges (Annex C). Our generator must never produce these; the
# loader must accept them, because judges load their own data with them.
RESERVED_ACCOUNT_RANGE: tuple[int, int] = (9000, 9999)
RESERVED_INVOICE_PREFIX = "INV-J"
RESERVED_SOURCE_PREFIX = "JD-"

_DATE_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
_PERIOD_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]"


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    owner_email: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    product_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("account_id GLOB 'A[0-9][0-9][0-9][0-9]'", name="ck_accounts_account_id_format"),
        # "@example.com domains only": example.com or a subdomain (RFC 2606 reserved).
        CheckConstraint(
            "lower(owner_email) LIKE '%@example.com' OR lower(owner_email) LIKE '%@%.example.com'",
            name="ck_accounts_owner_email_example_domain",
        ),
        CheckConstraint(_in("plan", PLANS), name="ck_accounts_plan"),
        CheckConstraint(_in("status", ACCOUNT_STATUSES), name="ck_accounts_status"),
        CheckConstraint(f"created_at GLOB '{_DATE_GLOB}'", name="ck_accounts_created_at_format"),
        Index("ix_accounts_plan", "plan"),
        Index("ix_accounts_status", "status"),
    )


class PlanLimit(Base):
    __tablename__ = "plan_limits"

    plan: Mapped[str] = mapped_column(Text, primary_key=True)
    api_rate_limit_per_min: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_workflow_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    seats: Mapped[int] = mapped_column(Integer, nullable=False)
    support_tier: Mapped[str] = mapped_column(Text, nullable=False)
    monthly_price: Mapped[float] = mapped_column(REAL, nullable=False)

    __table_args__ = (
        CheckConstraint(_in("plan", PLANS), name="ck_plan_limits_plan"),
        CheckConstraint("api_rate_limit_per_min >= 0", name="ck_plan_limits_rate_non_negative"),
        CheckConstraint("monthly_workflow_runs >= 0", name="ck_plan_limits_runs_non_negative"),
        CheckConstraint("seats >= 0", name="ck_plan_limits_seats_non_negative"),
        CheckConstraint("monthly_price >= 0", name="ck_plan_limits_price_non_negative"),
    )


class Usage(Base):
    __tablename__ = "usage"

    account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("accounts.account_id"), primary_key=True
    )
    period: Mapped[str] = mapped_column(Text, primary_key=True)
    workflow_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    api_calls_peak_per_min: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_used: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint(f"period GLOB '{_PERIOD_GLOB}'", name="ck_usage_period_format"),
        CheckConstraint("workflow_runs >= 0", name="ck_usage_runs_non_negative"),
        CheckConstraint("api_calls_peak_per_min >= 0", name="ck_usage_api_non_negative"),
        CheckConstraint("seats_used >= 0", name="ck_usage_seats_non_negative"),
        Index("ix_usage_period", "period"),
    )


class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("accounts.account_id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(REAL, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    charged_on: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    card_last4: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_invoices_amount_positive"),
        CheckConstraint(f"charged_on GLOB '{_DATE_GLOB}'", name="ck_invoices_charged_on_format"),
        CheckConstraint(_in("status", INVOICE_STATUSES), name="ck_invoices_status"),
        CheckConstraint(
            "status = 'failed' OR failure_reason IS NULL", name="ck_invoices_failure_reason_only_if_failed"
        ),
        CheckConstraint(
            "card_last4 IS NULL OR card_last4 GLOB '[0-9][0-9][0-9][0-9]'", name="ck_invoices_card_last4_only"
        ),
        Index("ix_invoices_account_charged_on", "account_id", "charged_on"),
    )


class PlatformStatus(Base):
    __tablename__ = "platform_status"

    component: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    incident_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(_in("status", PLATFORM_STATUSES), name="ck_platform_status_status"),
        CheckConstraint(
            "status <> 'operational' OR incident_id IS NULL", name="ck_platform_status_incident_only_if_not_operational"
        ),
    )


class PolicyRule(Base):
    __tablename__ = "policy_registry"

    rule_id: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameter: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    scope_plans: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_section: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"effective_from GLOB '{_DATE_GLOB}'", name="ck_policy_effective_from_format"),
        Index("ix_policy_registry_parameter", "parameter"),
    )


class Handoff(Base):
    __tablename__ = "handoffs"

    handoff_id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    queue: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    bundle_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(_in("priority", HANDOFF_PRIORITIES), name="ck_handoffs_priority"),
        CheckConstraint("json_valid(bundle_json)", name="ck_handoffs_bundle_is_json"),
        Index("ix_handoffs_account_id", "account_id"),
        Index("ix_handoffs_conversation_id", "conversation_id"),
    )


# Mandatory tables required by the hackathon specification (Annex C), in
# dependency order (parents before children). Used for loading and health.
MANDATORY_TABLES: tuple[str, ...] = (
    "plan_limits",
    "accounts",
    "usage",
    "invoices",
    "platform_status",
    "policy_registry",
    "handoffs",
)

MODELS_BY_TABLE: dict[str, type[Base]] = {
    model.__tablename__: model
    for model in (PlanLimit, Account, Usage, Invoice, PlatformStatus, PolicyRule, Handoff)
}

# Kept for backwards compatibility with Phase 1 health reporting; empty now
# that every Annex C table is implemented.
PENDING_ANNEX_C_TABLES: tuple[str, ...] = ()


def missing_mandatory_tables(existing_tables: list[str] | set[str]) -> list[str]:
    """Return the mandatory tables not present in the database."""
    existing = set(existing_tables)
    return [name for name in MANDATORY_TABLES if name not in existing]
