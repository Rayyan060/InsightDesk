"""SQLAlchemy engine/session management for SQLite.

* Foreign keys are enforced on every connection (SQLite disables them by default).
* ``Database.session_scope()`` provides commit-on-success / rollback-on-error.
* ``get_db_session`` (in ``app.api.dependencies``) exposes a request-scoped
  session to FastAPI routes.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _enable_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_sqlite_engine(url: str, *, echo: bool = False) -> Engine:
    """Create an engine with FK enforcement.

    For file databases the parent directory is created if missing. In-memory
    databases use a StaticPool so every session sees the same database.
    """
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        raise ValueError("Only SQLite URLs are supported.")

    kwargs: dict[str, Any] = {
        "echo": echo,
        "future": True,
        "connect_args": {"check_same_thread": False},
    }
    database = parsed.database
    if not database or database == ":memory:":
        kwargs["poolclass"] = StaticPool
    else:
        Path(database).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, **kwargs)
    event.listen(engine, "connect", _enable_sqlite_pragmas)
    return engine


@dataclass
class DatabaseStatus:
    connected: bool
    foreign_keys_enabled: bool = False
    existing_tables: list[str] = field(default_factory=list)
    schema_problems: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    error: str | None = None


class Database:
    """Owns the engine and session factory for the application lifetime."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        self.engine = create_sqlite_engine(url, echo=echo)
        self.session_factory = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False, class_=Session
        )

    def init_schema(self) -> None:
        """Create any missing Annex C tables (``CREATE TABLE`` only for absent tables).

        Never drops or alters existing tables, so existing data survives. If
        the schema ever needs to evolve, add Alembic migrations instead.
        """
        # Import so every model module registers itself on Base.metadata.
        from app.database import models  # noqa: F401

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check(self) -> DatabaseStatus:
        """Run a real round-trip query. Never raises."""
        from app.database.annex_c import ANNEX_C_SCHEMA, verify_schema

        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
                tables = sorted(inspect(conn).get_table_names())
                counts = {
                    # Table names come from the Annex C constant, never from input.
                    t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar_one()
                    for t in ANNEX_C_SCHEMA
                    if t in tables
                }
            return DatabaseStatus(
                connected=True,
                foreign_keys_enabled=bool(fk),
                existing_tables=tables,
                schema_problems=verify_schema(self.engine),
                row_counts=counts,
            )
        except Exception as exc:
            return DatabaseStatus(connected=False, error=type(exc).__name__)

    def dispose(self) -> None:
        self.engine.dispose()
