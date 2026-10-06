"""Row-level validation models for the Annex C tables.

One Pydantic model per table, with exactly the Annex C column names. These
models are the single source of truth for per-row rules, shared by:

* the synthetic data generator (seeded and LLM). LLM output is parsed with
  them, and their JSON Schema is sent to Ollama as the required output format;
* the dataset validator (``app.database.validation``);
* the CSV loader (``app.database.csv_io``).

Normalisation: values are whitespace-stripped, and enumerations are matched
case-insensitively, then stored in the canonical Annex C spelling ("pro" becomes
"Pro", "PAID" becomes "paid"). Blank optional cells become ``None``.

Error messages never include the rejected value, which may be PII (emails) or
something dangerous (a full card number).
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.database.models import (
    ACCOUNT_STATUSES,
    HANDOFF_PRIORITIES,
    INVOICE_STATUSES,
    PLANS,
    PLATFORM_STATUSES,
)

SUPPORTED_POLICY_OPERATORS: tuple[str, ...] = ("<", "<=", ">", ">=", "==", "!=", "in", "not_in")

_ACCOUNT_ID_RE = re.compile(r"^A\d{4}$")
_GENERIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)*example\.com$", re.IGNORECASE)
_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_CARD_LAST4_RE = re.compile(r"^\d{4}$")
_PARAMETER_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_RULE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")


# ---------------------------------------------------------------------- #
# Reusable field types
# ---------------------------------------------------------------------- #
def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _canonical(choices: tuple[str, ...], label: str):
    lookup = {c.lower(): c for c in choices}

    def convert(value: Any) -> Any:
        if isinstance(value, str):
            canonical = lookup.get(value.strip().lower())
            if canonical is None:
                raise ValueError(f"{label} must be one of {list(choices)}")
            return canonical
        return value

    return convert


def _check_date(value: str) -> str:
    if not _DATE_RE.fullmatch(value):
        raise ValueError("must be a date in YYYY-MM-DD format")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("is not a valid calendar date") from None
    return value


def _check_timestamp(value: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("must be an ISO 8601 timestamp") from None
    return value


def _check_pattern(pattern: re.Pattern[str], message: str):
    def check(value: str) -> str:
        if not pattern.fullmatch(value):
            raise ValueError(message)
        return value

    return check


def _optional(check):
    """Apply ``check`` only when a value is present."""

    def wrapper(value: str | None) -> str | None:
        return None if value is None else check(value)

    return wrapper


def _check_operator(value: str) -> str:
    if value not in SUPPORTED_POLICY_OPERATORS:
        raise ValueError(f"must be one of {list(SUPPORTED_POLICY_OPERATORS)}")
    return value


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("must be a finite number")
    return value


OptionalText = Annotated[str | None, BeforeValidator(_blank_to_none)]
RequiredText = Annotated[str, BeforeValidator(_blank_to_none), Field(min_length=1, max_length=500)]
IsoDate = Annotated[str, BeforeValidator(_blank_to_none), AfterValidator(_check_date)]
IsoTimestamp = Annotated[str, BeforeValidator(_blank_to_none), AfterValidator(_check_timestamp)]
AccountId = Annotated[
    str,
    BeforeValidator(_blank_to_none),
    AfterValidator(_check_pattern(_ACCOUNT_ID_RE, "must be 'A' followed by 4 digits (e.g. A1001)")),
]
GenericId = Annotated[
    str,
    BeforeValidator(_blank_to_none),
    AfterValidator(_check_pattern(_GENERIC_ID_RE, "must be 1-64 characters: letters, digits, '-' or '_'")),
]
Plan = Annotated[str, BeforeValidator(_canonical(PLANS, "plan"))]
NonNegativeInt = Annotated[int, Field(ge=0)]


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------- #
# Annex C tables
# ---------------------------------------------------------------------- #
class AccountRow(_Row):
    account_id: AccountId
    company_name: RequiredText
    owner_email: Annotated[
        str,
        BeforeValidator(_blank_to_none),
        AfterValidator(_check_pattern(_EMAIL_RE, "must be a synthetic address on an example.com domain")),
    ]
    plan: Plan
    status: Annotated[str, BeforeValidator(_canonical(ACCOUNT_STATUSES, "status"))]
    product_version: Annotated[
        str,
        BeforeValidator(_blank_to_none),
        AfterValidator(_check_pattern(_VERSION_RE, "must look like 4.3 or 3.9.1")),
    ]
    created_at: IsoDate


class PlanLimitRow(_Row):
    plan: Plan
    api_rate_limit_per_min: NonNegativeInt
    monthly_workflow_runs: NonNegativeInt
    seats: NonNegativeInt
    support_tier: RequiredText
    monthly_price: Annotated[float, Field(ge=0), AfterValidator(_finite)]


class UsageRow(_Row):
    account_id: AccountId
    period: Annotated[
        str,
        BeforeValidator(_blank_to_none),
        AfterValidator(_check_pattern(_PERIOD_RE, "must be a month in YYYY-MM format")),
    ]
    workflow_runs: NonNegativeInt
    api_calls_peak_per_min: NonNegativeInt
    seats_used: NonNegativeInt


class InvoiceRow(_Row):
    invoice_id: GenericId
    account_id: AccountId
    amount: Annotated[float, Field(gt=0), AfterValidator(_finite)]
    currency: Annotated[
        str,
        BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
        AfterValidator(_check_pattern(_CURRENCY_RE, "must be a 3-letter ISO currency code")),
    ]
    charged_on: IsoDate
    status: Annotated[str, BeforeValidator(_canonical(INVOICE_STATUSES, "status"))]
    failure_reason: OptionalText = None
    card_last4: Annotated[
        str | None,
        BeforeValidator(_blank_to_none),
        AfterValidator(
            _optional(
                _check_pattern(
                    _CARD_LAST4_RE, "must be exactly the last four digits; full card numbers must never be stored"
                )
            )
        ),
    ] = None

    @model_validator(mode="after")
    def _failure_reason_only_if_failed(self) -> "InvoiceRow":
        if self.status != "failed" and self.failure_reason is not None:
            raise ValueError("failure_reason must be empty unless status is 'failed'")
        return self


class PlatformStatusRow(_Row):
    component: Annotated[str, BeforeValidator(_blank_to_none), Field(min_length=1, max_length=64)]
    status: Annotated[str, BeforeValidator(_canonical(PLATFORM_STATUSES, "status"))]
    incident_id: OptionalText = None
    updated_at: IsoTimestamp

    @model_validator(mode="after")
    def _incident_only_if_not_operational(self) -> "PlatformStatusRow":
        if self.status == "operational" and self.incident_id is not None:
            raise ValueError("incident_id must be empty when status is 'operational'")
        return self


def _check_scope_plans(value: str) -> str:
    if value.upper() == "ALL":
        return "ALL"
    parts = [p.strip() for p in re.split(r"[;,]", value) if p.strip()]
    if not parts:
        raise ValueError("must be ALL or a list of plans")
    canonical = [_canonical(PLANS, "scope_plans entry")(p) for p in parts]
    return ";".join(canonical)


class PolicyRuleRow(_Row):
    rule_id: Annotated[
        str,
        BeforeValidator(_blank_to_none),
        AfterValidator(_check_pattern(_RULE_ID_RE, "must look like REFUND-WINDOW-01")),
    ]
    description: RequiredText
    parameter: Annotated[
        str,
        BeforeValidator(_blank_to_none),
        AfterValidator(_check_pattern(_PARAMETER_RE, "must be snake_case, e.g. refund_window_days")),
    ]
    operator: Annotated[str, BeforeValidator(_blank_to_none), AfterValidator(_check_operator)]
    value: RequiredText
    scope_plans: Annotated[str, BeforeValidator(_blank_to_none), AfterValidator(_check_scope_plans)]
    effective_from: IsoDate
    source_id: GenericId
    source_section: OptionalText = None


class HandoffRow(_Row):
    handoff_id: GenericId
    conversation_id: Annotated[
        str | None,
        BeforeValidator(_blank_to_none),
        AfterValidator(
            _optional(_check_pattern(_GENERIC_ID_RE, "must be 1-64 characters: letters, digits, '-' or '_'"))
        ),
    ] = None
    account_id: Annotated[
        str | None,
        BeforeValidator(_blank_to_none),
        AfterValidator(_optional(_check_pattern(_ACCOUNT_ID_RE, "must be 'A' followed by 4 digits"))),
    ] = None
    queue: Annotated[str, BeforeValidator(_blank_to_none), Field(min_length=1, max_length=64)]
    priority: Annotated[str, BeforeValidator(_canonical(HANDOFF_PRIORITIES, "priority"))]
    created_at: IsoTimestamp
    bundle_json: str

    @model_validator(mode="after")
    def _bundle_is_json_object(self) -> "HandoffRow":
        try:
            parsed = json.loads(self.bundle_json)
        except (TypeError, ValueError):
            raise ValueError("bundle_json must be valid JSON") from None
        if not isinstance(parsed, dict):
            raise ValueError("bundle_json must be a JSON object")
        return self


ROW_MODELS: dict[str, type[_Row]] = {
    "plan_limits": PlanLimitRow,
    "accounts": AccountRow,
    "usage": UsageRow,
    "invoices": InvoiceRow,
    "platform_status": PlatformStatusRow,
    "policy_registry": PolicyRuleRow,
    "handoffs": HandoffRow,
}

# Primary-key columns per table (Annex C).
PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "plan_limits": ("plan",),
    "accounts": ("account_id",),
    "usage": ("account_id", "period"),
    "invoices": ("invoice_id",),
    "platform_status": ("component",),
    "policy_registry": ("rule_id",),
    "handoffs": ("handoff_id",),
}


def required_columns(table: str) -> list[str]:
    model = ROW_MODELS[table]
    return [name for name, field in model.model_fields.items() if field.is_required()]


def all_columns(table: str) -> list[str]:
    return list(ROW_MODELS[table].model_fields)
