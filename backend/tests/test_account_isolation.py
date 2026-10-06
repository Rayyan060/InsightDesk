"""Account-scoped repository access (R8) and parameterised queries."""

from __future__ import annotations

import inspect

import pytest

from app.core.exceptions import AccountContextError
from app.core.security import AccountContext, parse_account_id
from app.database.csv_io import ConflictPolicy, import_csv_files
from app.database.repositories import AccountScopedRepository
from app.synthetic.pipeline import SYNTHETIC_DIR, REFERENCE_DIR


@pytest.fixture
def loaded_db(db):
    files = {
        "plan_limits": REFERENCE_DIR / "plan_limits.csv",
        "policy_registry": REFERENCE_DIR / "policy_registry.csv",
        "accounts": SYNTHETIC_DIR / "accounts.csv",
        "usage": SYNTHETIC_DIR / "usage.csv",
        "invoices": SYNTHETIC_DIR / "invoices.csv",
    }
    assert import_csv_files(db.engine, files, conflict=ConflictPolicy.ERROR).committed
    return db


def _repo(session, account_id: str) -> AccountScopedRepository:
    return AccountScopedRepository(session, AccountContext(account_id=account_id))


def test_repository_returns_only_the_context_account(loaded_db) -> None:
    with loaded_db.session_scope() as session:
        a, b = _repo(session, "A1001"), _repo(session, "A1010")
        assert a.account().account_id == "A1001"
        assert {i.account_id for i in a.invoices()} == {"A1001"}
        assert {u.account_id for u in a.usage()} == {"A1001"}
        other_invoice = b.invoices()[0].invoice_id
        assert a.invoice(other_invoice) is None  # same answer as "doesn't exist": no leak
        assert b.invoice(other_invoice) is not None


def test_unknown_account_sees_nothing(loaded_db) -> None:
    with loaded_db.session_scope() as session:
        repo = _repo(session, "A8999")
        assert repo.account() is None and repo.invoices() == [] and repo.usage() == []


def test_injection_strings_are_bound_parameters_not_sql(loaded_db) -> None:
    with loaded_db.session_scope() as session:
        repo = _repo(session, "A1001' OR '1'='1")
        assert repo.invoices() == [] and repo.account() is None
        assert _repo(session, "A1001").invoice("x' OR '1'='1") is None


def test_header_validation_rejects_injection_strings() -> None:
    with pytest.raises(AccountContextError):
        parse_account_id("A1001' OR '1'='1")


def test_no_scoped_method_accepts_an_account_id() -> None:
    for name, method in inspect.getmembers(AccountScopedRepository, inspect.isfunction):
        if name.startswith("_"):
            continue
        assert "account_id" not in inspect.signature(method).parameters, name


def test_invoice_filters_and_ordering(loaded_db) -> None:
    with loaded_db.session_scope() as session:
        repo = _repo(session, "A1010")  # duplicate-charge account in the dataset of record
        invoices = repo.invoices()
        assert [i.charged_on for i in invoices] == sorted((i.charged_on for i in invoices), reverse=True)
        assert len(repo.invoices(limit=2)) == 2
        assert all(i.status == "paid" for i in repo.invoices(status="paid"))
