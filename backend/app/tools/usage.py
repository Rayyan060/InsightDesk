"""get_usage and get_plan_limits (tables: usage, plan_limits, policy_registry)."""

from __future__ import annotations

from app.core.exceptions import NotImplementedFeatureError
from app.schemas.tools import GetPlanLimitsRequest, GetUsageRequest, PlanLimitsResult, UsageReport
from app.tools.base import ToolContext


def get_usage(ctx: ToolContext, request: GetUsageRequest) -> UsageReport:
    """Usage for one period compared with plan limits.

    Utilisation and state (within / approaching / at / over) are computed in
    code using QUOTA-APPROACHING-01 and QUOTA-OVER-01 from the policy registry:
    exactly at the limit is "at_limit", and one unit over is "over_limit".
    """
    raise NotImplementedFeatureError("Tool get_usage", planned_phase="Phase 5")


def get_plan_limits(ctx: ToolContext, request: GetPlanLimitsRequest) -> PlanLimitsResult:
    raise NotImplementedFeatureError("Tool get_plan_limits", planned_phase="Phase 5")
