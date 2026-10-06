"""lookup_account and send_password_reset (tables: accounts)."""

from __future__ import annotations

from app.core.exceptions import NotImplementedFeatureError
from app.schemas.tools import AccountSummary, LookupAccountRequest, PasswordResetResult, SendPasswordResetRequest
from app.tools.base import ToolContext


def lookup_account(ctx: ToolContext, request: LookupAccountRequest) -> AccountSummary:
    """Account facts for the header account; owner email returned masked only."""
    raise NotImplementedFeatureError("Tool lookup_account", planned_phase="Phase 5")


def send_password_reset(ctx: ToolContext, request: SendPasswordResetRequest) -> PasswordResetResult:
    """Mocked: records that a reset email *would* be sent to the owner email on file.

    Never generates, stores or returns a token or link. There is no argument
    for a destination address, so a reset can't be redirected.
    """
    raise NotImplementedFeatureError("Tool send_password_reset", planned_phase="Phase 5")
