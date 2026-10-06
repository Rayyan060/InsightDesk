"""Account-scoped data access (R8: the account comes only from X-Account-Id).

``AccountScopedRepository`` is constructed from the validated
``AccountContext`` of the request. None of its methods takes an account ID,
so code that only holds this repository (the tools) cannot read another
account's data, even if a customer message or the LLM names a different
account. Every query filters by ``ctx.account_id`` through bound parameters.

Looking up a record that belongs to a different account returns ``None``,
exactly as for a record that doesn't exist, so existence isn't leaked.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AccountContext
from app.database.models import Account, Handoff, Invoice, PlanLimit, PlatformStatus, Usage
from app.database.repositories.base import BaseRepository
from app.database.row_schemas import AccountRow, HandoffRow, InvoiceRow, PlanLimitRow, PlatformStatusRow, UsageRow


class AccountScopedRepository(BaseRepository):
    def __init__(self, session: Session, ctx: AccountContext) -> None:
        super().__init__(session)
        self._account_id = ctx.account_id

    @property
    def account_id(self) -> str:
        return self._account_id

    def account(self) -> AccountRow | None:
        row = self.session.get(Account, self._account_id)
        return AccountRow.model_validate(row, from_attributes=True) if row else None

    def usage(self, period: str | None = None) -> list[UsageRow]:
        stmt = select(Usage).where(Usage.account_id == self._account_id)
        if period is not None:
            stmt = stmt.where(Usage.period == period)
        rows = self.session.execute(stmt.order_by(Usage.period)).scalars()
        return [UsageRow.model_validate(r, from_attributes=True) for r in rows]

    def invoices(self, *, status: str | None = None, limit: int | None = None) -> list[InvoiceRow]:
        stmt = select(Invoice).where(Invoice.account_id == self._account_id)
        if status is not None:
            stmt = stmt.where(Invoice.status == status)
        stmt = stmt.order_by(Invoice.charged_on.desc(), Invoice.invoice_id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return [InvoiceRow.model_validate(r, from_attributes=True) for r in self.session.execute(stmt).scalars()]

    def invoice(self, invoice_id: str) -> InvoiceRow | None:
        stmt = select(Invoice).where(Invoice.invoice_id == invoice_id, Invoice.account_id == self._account_id)
        row = self.session.execute(stmt).scalar_one_or_none()
        return InvoiceRow.model_validate(row, from_attributes=True) if row else None

    def handoffs(self) -> list[HandoffRow]:
        stmt = select(Handoff).where(Handoff.account_id == self._account_id).order_by(Handoff.created_at)
        return [HandoffRow.model_validate(r, from_attributes=True) for r in self.session.execute(stmt).scalars()]


class ReferenceRepository(BaseRepository):
    """Non-account data: plan limits and platform status."""

    def plan_limits(self, plan: str) -> PlanLimitRow | None:
        row = self.session.get(PlanLimit, plan)
        return PlanLimitRow.model_validate(row, from_attributes=True) if row else None

    def all_plan_limits(self) -> list[PlanLimitRow]:
        rows = self.session.execute(select(PlanLimit).order_by(PlanLimit.monthly_price)).scalars()
        return [PlanLimitRow.model_validate(r, from_attributes=True) for r in rows]

    def platform_status(self, component: str | None = None) -> list[PlatformStatusRow]:
        stmt = select(PlatformStatus).order_by(PlatformStatus.component)
        if component is not None:
            stmt = stmt.where(PlatformStatus.component == component)
        return [PlatformStatusRow.model_validate(r, from_attributes=True) for r in self.session.execute(stmt).scalars()]


class HandoffRepository(BaseRepository):
    """Handoffs are written only by the create_handoff tool (Phase 5)."""

    def add(self, row: HandoffRow) -> None:
        self.session.add(Handoff(**row.model_dump()))

    def get(self, handoff_id: str) -> HandoffRow | None:
        row = self.session.get(Handoff, handoff_id)
        return HandoffRow.model_validate(row, from_attributes=True) if row else None
