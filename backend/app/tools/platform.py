"""check_platform_status (table: platform_status). Not account-scoped."""

from __future__ import annotations

from app.core.exceptions import NotImplementedFeatureError
from app.schemas.tools import CheckPlatformStatusRequest, PlatformStatusResult
from app.tools.base import ToolContext


def check_platform_status(ctx: ToolContext, request: CheckPlatformStatusRequest) -> PlatformStatusResult:
    raise NotImplementedFeatureError("Tool check_platform_status", planned_phase="Phase 5")
