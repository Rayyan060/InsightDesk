"""Exact Annex C schema, constraints, FK enforcement, uniqueness, initialisation."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database.annex_c import ANNEX_C_SCHEMA, verify_schema
from app.database.connection import Database
from app.database.csv_io import table_counts
from app.database.init_db import initialize_database
from app.database.models import MANDATORY_TABLES

ACCOUNT = {
    "account_id": "A1001", "company_name": "Aster Labs", "owner_email": "a.b@example.com",
    "plan": "Pro", "status": "active", "product_version": "4.3", "created_at": "2026-01-05",
}
PLAN = {"plan": "Pro", "api_rate_limit_per_min": 600, "monthly_workflow_runs": 20000, "seats": 10, "support_tier": "standard", "monthly_price": 49.0}
INVOICE = {
    "invoice_id": "INV-6001", "account_id": "A1001", "amount": 49.0, "currency": "USD",
    "charged_on": "2026-10-01", "status": "paid", "failure_reason": None, "card_last4": "4242",
}


def _insert(db: Database, table: str, row: dict) -> None:
    columns = ", ".join(row)
    params = ", ".join(f":{c}" for c in row)
    with db.engine.begin() as conn:
        conn.execute(text(f'INSERT INTO "{table}" ({columns}) VALUES ({params})'), row)


# --- exact schema -----------------------------------------------------------
def test_schema_matches_annex_c_transcription(db) -> None:
    assert verify_schema(db.engine) == []


@pytest.mark.parametrize("table", list(ANNEX_C_SCHEMA))
def test_exact_columns_types_and_primary_keys(db, table) -> None:
    with db.engine.connect() as conn:
        info = conn.execute(text(f'PRAGMA table_info("{table}")')).all()
    actual = [(r[1], r[2].upper(), bool(r[5])) for r in info]
    expected = [(c.name, c.type, c.pk) for c in ANNEX_C_SCHEMA[table]]
    assert actual == expected  # same names, same order, same types, same PKs; nothing renamed or removed


def test_foreign_keys_exactly_as_annex_c(db) -> None:
    insp = inspect(db.engine)
    for table in ANNEX_C_SCHEMA:
        fks = {(fk["constrained_columns"][0], f"{fk['referred_table']}.{fk['referred_columns'][0]}") for fk in insp.get_foreign_keys(table)}
        expected = {(c.name, c.fk) for c in ANNEX_C_SCHEMA[table] if c.fk}
        assert fks == expected, table


def test_indexes_for_frequent_queries(db) -> None:
    insp = inspect(db.engine)
    names = {ix["name"] for t in ANNEX_C_SCHEMA for ix in insp.get_indexes(t)}
    assert {"ix_invoices_account_charged_on", "ix_handoffs_account_id", "ix_policy_registry_parameter", "ix_usage_period"} <= names


def test_verify_schema_detects_drift(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'drift.db').as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, company TEXT, plan INTEGER)"))
    problems = verify_schema(engine)
    assert "accounts.company_name: column missing" in problems
    assert "accounts.plan: type INTEGER, expected TEXT" in problems
    assert "usage: table missing" in problems


# --- constraints --------------------------------------------------------------
def test_foreign_key_enforced_for_invoices_and_usage(db) -> None:
    with pytest.raises(IntegrityError):
        _insert(db, "invoices", INVOICE)
    with pytest.raises(IntegrityError):
        _insert(db, "usage", {"account_id": "A1999", "period": "2026-10", "workflow_runs": 1, "api_calls_peak_per_min": 1, "seats_used": 1})


@pytest.mark.parametrize(
    ("table", "row"),
    [
        ("accounts", ACCOUNT),
        ("plan_limits", PLAN),
        ("usage", {"account_id": "A1001", "period": "2026-10", "workflow_runs": 1, "api_calls_peak_per_min": 1, "seats_used": 1}),
        ("invoices", INVOICE),
    ],
)
def test_primary_keys_are_unique(db, table, row) -> None:
    if table in ("usage", "invoices"):
        _insert(db, "accounts", ACCOUNT)
    _insert(db, table, row)
    with pytest.raises(IntegrityError):
        _insert(db, table, row)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"amount": 0}, "amount > 0"),
        ({"amount": -5.0}, "amount > 0"),
        ({"card_last4": "4111111111111111"}, "full card numbers never stored"),
        ({"failure_reason": "card_declined"}, "failure_reason only when failed"),
        ({"status": "pending"}, "status enumeration"),
        ({"charged_on": "01/10/2026"}, "date format"),
    ],
)
def test_invoice_check_constraints(db, change, reason) -> None:
    _insert(db, "accounts", ACCOUNT)
    with pytest.raises(IntegrityError):
        _insert(db, "invoices", {**INVOICE, **change})


@pytest.mark.parametrize(
    "change",
    [{"account_id": "1001"}, {"account_id": "A10011"}, {"plan": "Gold"}, {"status": "deleted"}, {"owner_email": "x@gmail.com"}],
)
def test_account_check_constraints(db, change) -> None:
    with pytest.raises(IntegrityError):
        _insert(db, "accounts", {**ACCOUNT, **change})


def test_platform_status_incident_only_when_not_operational(db) -> None:
    with pytest.raises(IntegrityError):
        _insert(db, "platform_status", {"component": "api", "status": "operational", "incident_id": "INC-1", "updated_at": "2026-10-06T08:00:00Z"})
    _insert(db, "platform_status", {"component": "api", "status": "degraded", "incident_id": "INC-1", "updated_at": "2026-10-06T08:00:00Z"})


def test_handoff_bundle_must_be_json(db) -> None:
    row = {"handoff_id": "H-0001", "conversation_id": "C-1", "account_id": "A1001", "queue": "billing", "priority": "high", "created_at": "2026-10-06T08:00:00Z"}
    with pytest.raises(IntegrityError):
        _insert(db, "handoffs", {**row, "bundle_json": "not json"})
    _insert(db, "handoffs", {**row, "bundle_json": '{"pii_redacted": true}'})


def test_reserved_judge_ids_are_storable(db) -> None:
    """Judges load A9000-A9999 / INV-J... into this exact schema."""
    _insert(db, "accounts", {**ACCOUNT, "account_id": "A9001"})
    _insert(db, "invoices", {**INVOICE, "invoice_id": "INV-J001", "account_id": "A9001"})


# --- initialisation -----------------------------------------------------------
def test_initialisation_is_idempotent_and_preserves_data(tmp_path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'init.db').as_posix()}")
    try:
        first = initialize_database(database)
        assert first.ok and first.reference_import.tables["policy_registry"].inserted == 23
        _insert(database, "accounts", ACCOUNT)
        with database.engine.begin() as conn:  # an operator edit to reference data
            conn.execute(text("UPDATE plan_limits SET seats = 12 WHERE plan = 'Pro'"))

        second = initialize_database(database)
        counts = table_counts(database.engine)
        assert counts["accounts"] == 1  # user data not dropped
        assert counts["plan_limits"] == 4 and counts["policy_registry"] == 23  # no duplicates
        assert second.reference_import.tables["policy_registry"].unchanged == 23
        assert second.reference_import.tables["plan_limits"].skipped == 1  # edited row kept, not overwritten
        with database.engine.connect() as conn:
            assert conn.execute(text("SELECT seats FROM plan_limits WHERE plan='Pro'")).scalar() == 12
    finally:
        database.dispose()


def test_session_scope_rolls_back_multi_record_writes(db) -> None:
    from app.database.models import Account, Invoice

    with pytest.raises(IntegrityError):
        with db.session_scope() as session:
            session.add(Account(**ACCOUNT))
            session.flush()
            session.add(Invoice(**{**INVOICE, "amount": -1.0}))
            session.flush()
    assert table_counts(db.engine)["accounts"] == 0


def test_mandatory_table_order_is_dependency_safe() -> None:
    assert MANDATORY_TABLES.index("accounts") < MANDATORY_TABLES.index("usage") < MANDATORY_TABLES.index("invoices")
    assert set(MANDATORY_TABLES) == set(ANNEX_C_SCHEMA)
