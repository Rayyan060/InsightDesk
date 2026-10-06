"""8: SQLite connectivity, FK enforcement, transactions and session DI."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, text
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DbSessionDep
from app.database.connection import Database
from app.database.models import MANDATORY_TABLES, missing_mandatory_tables


@pytest.fixture
def database(tmp_path) -> Database:
    db = Database(f"sqlite:///{(tmp_path / 'nested' / 'db.sqlite').as_posix()}")
    yield db
    db.dispose()


def test_connects_and_creates_parent_directory(database, tmp_path) -> None:
    status = database.check()
    assert status.connected
    assert (tmp_path / "nested").is_dir()


def test_foreign_keys_enabled_on_every_connection(database) -> None:
    for _ in range(3):
        with database.engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_foreign_key_violation_is_rejected(database) -> None:
    metadata = MetaData()
    parent = Table("parent", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "child",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("parent.id"), nullable=False),
    )
    metadata.create_all(database.engine)

    with pytest.raises(IntegrityError):
        with database.session_scope() as session:
            session.execute(child.insert().values(id=1, parent_id=999))

    with database.session_scope() as session:
        session.execute(parent.insert().values(id=1))
        session.execute(child.insert().values(id=1, parent_id=1))


def test_session_scope_rolls_back_on_error(database) -> None:
    with database.engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError):
        with database.session_scope() as session:
            session.execute(text("INSERT INTO t (id) VALUES (1)"))
            raise RuntimeError("abort")

    with database.session_scope() as session:
        assert session.execute(text("SELECT COUNT(*) FROM t")).scalar() == 0


def test_in_memory_database_shares_state_across_sessions() -> None:
    db = Database("sqlite://")
    with db.session_scope() as session:
        session.execute(text("CREATE TABLE t (id INTEGER)"))
        session.execute(text("INSERT INTO t VALUES (1)"))
    with db.session_scope() as session:
        assert session.execute(text("SELECT COUNT(*) FROM t")).scalar() == 1
    db.dispose()


def test_init_schema_creates_all_mandatory_tables(database) -> None:
    # Phase 1 asserted the tables were absent (Annex C pending); Phase 2 implements them.
    assert missing_mandatory_tables(database.check().existing_tables) == list(MANDATORY_TABLES)
    database.init_schema()
    assert missing_mandatory_tables(database.check().existing_tables) == []


def test_db_session_dependency(make_settings, build_client) -> None:
    def add_route(app: FastAPI) -> None:
        @app.get("/_db")
        def db_probe(session: DbSessionDep) -> dict:
            return {"value": session.execute(text("SELECT 41 + 1")).scalar()}

    client = build_client(make_settings(), configure=add_route)
    assert client.get("/_db").json() == {"value": 42}


def test_db_session_dependency_unavailable_when_not_configured(make_settings, build_client) -> None:
    def add_route(app: FastAPI) -> None:
        @app.get("/_db")
        def db_probe(session: DbSessionDep) -> dict:
            return {}

    client = build_client(make_settings(database_url=""), configure=add_route)
    response = client.get("/_db")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
