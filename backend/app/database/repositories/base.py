"""Repository base class.

Repositories encapsulate all SQL for one aggregate and receive a session from
the caller; they never commit. Transaction boundaries belong to the request
dependency (``get_db_session``) or ``Database.session_scope()``.

Concrete repositories (accounts, invoices, usage, plan_limits,
platform_status, policy_registry, handoffs) are added in Phase 2 once the
Annex C schema is implemented.
"""

from __future__ import annotations

from sqlalchemy.orm import Session


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
