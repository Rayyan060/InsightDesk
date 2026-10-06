"""Tool execution context and error type shared by all tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.security import AccountContext
from app.database.repositories import AccountScopedRepository
from app.schemas.tools import ToolErrorCode


@dataclass(frozen=True)
class ToolContext:
    """Everything a tool may use. Built by the API layer from the validated request.

    ``account`` comes only from the X-Account-Id header (R8). Tools must never
    take an account ID from arguments, message text or model output.
    """

    session: Session
    as_of_date: date
    trace_id: str
    account: AccountContext | None = None

    def scoped(self) -> AccountScopedRepository:
        if self.account is None:
            raise ToolFailure(ToolErrorCode.ACCOUNT_CONTEXT_REQUIRED, "this tool needs the X-Account-Id account")
        return AccountScopedRepository(self.session, self.account)


class ToolFailure(Exception):
    """Raised by tool implementations; converted to a ToolError by the dispatcher."""

    def __init__(self, code: ToolErrorCode, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
