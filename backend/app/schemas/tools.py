"""Typed contracts for the eight required tools (Annex C, "Required tools").

Account-scoping rule (R8): no request model contains an account ID. Account-
scoped tools act on the validated ``AccountContext`` from the X-Account-Id
header, which the dispatcher (``app.tools.registry``) supplies. Request models
forbid unknown fields, so an ``account_id`` injected by the LLM is rejected,
not silently ignored.

Response models describe real tool output. Implementations arrive in Phase 5;
until then the dispatcher returns a ``not_implemented`` error and never
fabricates a result.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator

from app.schemas.handoff import HandoffBundle, HandoffPriority, HandoffQueue


class ToolName(str, Enum):
    LOOKUP_ACCOUNT = "lookup_account"
    GET_USAGE = "get_usage"
    GET_PLAN_LIMITS = "get_plan_limits"
    GET_INVOICES = "get_invoices"
    CHECK_REFUND_ELIGIBILITY = "check_refund_eligibility"
    CHECK_PLATFORM_STATUS = "check_platform_status"
    SEND_PASSWORD_RESET = "send_password_reset"
    CREATE_HANDOFF = "create_handoff"


class ToolErrorCode(str, Enum):
    ACCOUNT_CONTEXT_REQUIRED = "account_context_required"  # no X-Account-Id for an account-scoped tool
    ACCOUNT_NOT_FOUND = "account_not_found"  # header account doesn't exist
    NOT_FOUND = "not_found"  # requested record doesn't exist for this account
    INVALID_ARGUMENTS = "invalid_arguments"  # arguments failed the request schema
    UNKNOWN_TOOL = "unknown_tool"
    DATA_UNAVAILABLE = "data_unavailable"  # database or reference data unavailable
    NOT_IMPLEMENTED = "not_implemented"  # planned for a later phase
    INTERNAL_ERROR = "internal_error"


class ToolError(BaseModel):
    code: ToolErrorCode
    message: str
    retryable: bool = False


class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class ToolInvocation(BaseModel):
    """One entry of ``tools_invoked`` (Section 6.1): ``{"tool": ..., "output": {...}}``.

    Failed calls carry ``error`` instead of ``output``, so a failure is never
    presented as data.
    """

    tool: str
    output: dict[str, Any] | list[Any] | None = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def _output_xor_error(self) -> "ToolInvocation":
        if (self.output is None) == (self.error is None):
            raise ValueError("a tool invocation has exactly one of output or error")
        return self

    @model_serializer(mode="wrap")
    def _section_6_1_shape(self, handler):  # type: ignore[no-untyped-def]
        # Success serialises as exactly {"tool", "output"}; failure as {"tool", "error"}.
        data = handler(self)
        data.pop("error" if self.error is None else "output", None)
        return data

    @property
    def status(self) -> ToolStatus:
        return ToolStatus.SUCCESS if self.error is None else ToolStatus.ERROR


class ToolResult(BaseModel):
    """Internal envelope kept in agent state (adds audit fields to ToolInvocation)."""

    tool: str
    status: ToolStatus
    output: dict[str, Any] | list[Any] | None = None
    error: ToolError | None = None
    source_tables: list[str] = Field(default_factory=list)
    latency_ms: float | None = Field(default=None, ge=0)


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Response(BaseModel):
    model_config = ConfigDict(extra="forbid")


_PERIOD = r"^\d{4}-(0[1-9]|1[0-2])$"


# 1. lookup_account ----------------------------------------------------------
class LookupAccountRequest(_Request):
    """No arguments: the account is the X-Account-Id account."""


class AccountSummary(_Response):
    account_id: str
    company_name: str
    plan: str
    status: str
    product_version: str
    created_at: date
    owner_email_masked: str = Field(description="e.g. n***@example.com. The full email is never returned (R9).")


# 2. get_usage ----------------------------------------------------------------
class GetUsageRequest(_Request):
    period: str | None = Field(default=None, pattern=_PERIOD, description="YYYY-MM; defaults to the as_of_date month.")


class UsageMetric(_Response):
    metric: Literal["workflow_runs", "api_calls_peak_per_min", "seats_used"]
    used: int = Field(ge=0)
    limit: int = Field(ge=0)
    utilization: float = Field(ge=0, description="used / limit, computed in code, never by the LLM.")
    state: Literal["within_limit", "approaching_limit", "at_limit", "over_limit"]


class UsageReport(_Response):
    account_id: str
    plan: str
    period: str
    metrics: list[UsageMetric]
    policy_rule_ids: list[str] = Field(default_factory=list, description="e.g. QUOTA-OVER-01, QUOTA-APPROACHING-01")


# 3. get_plan_limits ------------------------------------------------------------
class GetPlanLimitsRequest(_Request):
    plan: Literal["Free", "Pro", "Business", "Enterprise"] | None = Field(
        default=None, description="Defaults to the account's current plan."
    )


class PlanLimitsResult(_Response):
    plan: str
    api_rate_limit_per_min: int
    monthly_workflow_runs: int
    seats: int
    support_tier: str
    monthly_price: float


# 4. get_invoices ---------------------------------------------------------------
class GetInvoicesRequest(_Request):
    limit: int = Field(default=12, ge=1, le=50)
    status: Literal["paid", "failed", "refunded"] | None = None
    since: date | None = None


class InvoiceSummary(_Response):
    invoice_id: str
    amount: float = Field(gt=0)
    currency: str
    charged_on: date
    status: Literal["paid", "failed", "refunded"]
    failure_reason: str | None = None
    card_last4: str | None = Field(default=None, pattern=r"^\d{4}$")


class InvoiceList(_Response):
    account_id: str
    invoices: list[InvoiceSummary]
    total: int = Field(ge=0)


# 5. check_refund_eligibility -----------------------------------------------------
class CheckRefundEligibilityRequest(_Request):
    invoice_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", description="Defaults to the latest paid invoice."
    )


class RefundEligibilityResult(_Response):
    """Eligibility only. Refunds are never executed; every request goes to a human (R7)."""

    invoice_id: str
    eligible: bool
    reasons: list[str]
    as_of_date: date
    days_since_charge: int = Field(ge=0)
    refund_window_days: int | None = None
    policy_rule_ids: list[str]
    requires_human_approval: Literal[True] = True


# 6. check_platform_status --------------------------------------------------------
class CheckPlatformStatusRequest(_Request):
    component: str | None = Field(default=None, max_length=64)


class ComponentStatus(_Response):
    component: str
    status: Literal["operational", "degraded", "outage"]
    incident_id: str | None = None
    updated_at: str


class PlatformStatusResult(_Response):
    components: list[ComponentStatus]
    overall: Literal["operational", "degraded", "outage"]


# 7. send_password_reset ----------------------------------------------------------
_SECRET_LIKE = re.compile(r"(https?://|www\.|token|[A-Za-z0-9_\-]{24,})", re.IGNORECASE)


class SendPasswordResetRequest(_Request):
    """No arguments: the reset always goes to the owner email on file for the header account."""


class PasswordResetResult(_Response):
    """Mocked tool result. It has no token or link field, and its text fields are checked for them."""

    status: Literal["reset_email_sent", "account_not_eligible"]
    sent_to: str = Field(description="Masked address, e.g. n***@example.com")
    message: str

    @field_validator("sent_to", "message")
    @classmethod
    def _no_tokens_or_links(cls, value: str) -> str:
        if _SECRET_LIKE.search(value):
            raise ValueError("password-reset results must never contain a link or token (R9)")
        return value


# 8. create_handoff --------------------------------------------------------------
class CreateHandoffRequest(_Request):
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    queue: HandoffQueue
    priority: HandoffPriority
    bundle: HandoffBundle


class HandoffCreated(_Response):
    handoff_id: str
    queue: HandoffQueue
    priority: HandoffPriority
    created_at: str
