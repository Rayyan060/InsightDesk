"""Tool registry and dispatcher.

``TOOL_SPECS`` is the single description of every tool: request/response
models, whether it is account-scoped, and which tables it reads and writes
(documentation that tests check). ``invoke_tool`` is the only path from the
agent to a tool:

1. Unknown tool: ``unknown_tool`` error.
2. Arguments are validated against the request model. Unknown fields,
   including any attempt to pass ``account_id``, are rejected with
   ``invalid_arguments``.
3. An account-scoped tool without an X-Account-Id account gets
   ``account_context_required``.
4. The implementation runs, and its output is validated against the response
   model before it reaches the LLM or the customer.
5. Any failure becomes a structured ``ToolInvocation.error``, never fake output.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.exceptions import NotImplementedFeatureError
from app.schemas import tools as s
from app.schemas.tools import ToolError, ToolErrorCode, ToolInvocation, ToolName, ToolResult, ToolStatus
from app.tools import account, billing, handoff, platform, usage
from app.tools.base import ToolContext, ToolFailure

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    name: ToolName
    description: str
    request_model: type[BaseModel]
    response_model: type[BaseModel]
    implementation: Callable[[ToolContext, Any], BaseModel]
    account_scoped: bool
    reads: tuple[str, ...]
    writes: tuple[str, ...] = ()
    planned_phase: str = "Phase 5"


TOOL_SPECS: dict[ToolName, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(ToolName.LOOKUP_ACCOUNT, "Plan, status, product version and created date of the customer's account.",
                 s.LookupAccountRequest, s.AccountSummary, account.lookup_account, True, ("accounts",)),
        ToolSpec(ToolName.GET_USAGE, "Usage for a month compared with the plan limits.",
                 s.GetUsageRequest, s.UsageReport, usage.get_usage, True, ("usage", "accounts", "plan_limits", "policy_registry")),
        ToolSpec(ToolName.GET_PLAN_LIMITS, "Limits and price of a plan (default: the customer's plan).",
                 s.GetPlanLimitsRequest, s.PlanLimitsResult, usage.get_plan_limits, True, ("plan_limits", "accounts")),
        ToolSpec(ToolName.GET_INVOICES, "The customer's invoices, newest first.",
                 s.GetInvoicesRequest, s.InvoiceList, billing.get_invoices, True, ("invoices",)),
        ToolSpec(ToolName.CHECK_REFUND_ELIGIBILITY, "Whether an invoice is inside the refund window; never issues refunds.",
                 s.CheckRefundEligibilityRequest, s.RefundEligibilityResult, billing.check_refund_eligibility, True,
                 ("invoices", "accounts", "policy_registry")),
        ToolSpec(ToolName.CHECK_PLATFORM_STATUS, "Current status of CloudFlow components.",
                 s.CheckPlatformStatusRequest, s.PlatformStatusResult, platform.check_platform_status, False, ("platform_status",)),
        ToolSpec(ToolName.SEND_PASSWORD_RESET, "Mocked: send a reset email to the owner email on file; never returns a token or link.",
                 s.SendPasswordResetRequest, s.PasswordResetResult, account.send_password_reset, True, ("accounts",)),
        ToolSpec(ToolName.CREATE_HANDOFF, "Create a human handoff with a PII-redacted Annex D bundle.",
                 s.CreateHandoffRequest, s.HandoffCreated, handoff.create_handoff, False, ("accounts",), ("handoffs",)),
    )
}


def _error(code: ToolErrorCode, message: str, retryable: bool = False) -> ToolError:
    return ToolError(code=code, message=message, retryable=retryable)


def invoke_tool(name: str, ctx: ToolContext, arguments: dict[str, Any] | None = None) -> ToolResult:
    started = time.perf_counter()

    def done(output: Any = None, error: ToolError | None = None, tables: tuple[str, ...] = ()) -> ToolResult:
        result = ToolResult(
            tool=name,
            status=ToolStatus.SUCCESS if error is None else ToolStatus.ERROR,
            output=output,
            error=error,
            source_tables=list(tables),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        logger.info("tool_invoked", extra={"tool": name, "status": result.status.value, "error_code": error.code.value if error else None})
        return result

    try:
        spec = TOOL_SPECS[ToolName(name)]
    except ValueError:
        return done(error=_error(ToolErrorCode.UNKNOWN_TOOL, "unknown tool"))

    try:
        request = spec.request_model.model_validate(arguments or {})
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) or "arguments" for e in exc.errors(include_input=False)})
        return done(error=_error(ToolErrorCode.INVALID_ARGUMENTS, f"invalid arguments: {', '.join(fields)}"))

    if spec.account_scoped and ctx.account is None:
        return done(error=_error(ToolErrorCode.ACCOUNT_CONTEXT_REQUIRED, "this tool needs the X-Account-Id account"))

    try:
        response = spec.implementation(ctx, request)
        output = spec.response_model.model_validate(response.model_dump()).model_dump(mode="json")
    except NotImplementedFeatureError:
        return done(error=_error(ToolErrorCode.NOT_IMPLEMENTED, f"{spec.name.value} is not implemented yet ({spec.planned_phase})"))
    except ToolFailure as failure:
        return done(error=_error(failure.code, failure.message, failure.retryable))
    except ValidationError:
        return done(error=_error(ToolErrorCode.INTERNAL_ERROR, "tool produced output that violates its response schema"))
    except Exception as exc:  # database errors etc.
        logger.error("tool_failed", extra={"tool": name, "error_type": type(exc).__name__})
        return done(error=_error(ToolErrorCode.INTERNAL_ERROR, "tool failed", retryable=True))
    return done(output=output, tables=spec.reads)


def to_invocation(result: ToolResult) -> ToolInvocation:
    """Public ``tools_invoked`` entry (Section 6.1 shape)."""
    return ToolInvocation(tool=result.tool, output=result.output, error=result.error)
