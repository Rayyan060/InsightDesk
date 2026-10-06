"""Judge-compatible CSV loader: round trips, malformed input, FKs, duplicates, conflicts, transactions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.csv_io import (
    ConflictPolicy,
    dataset_from_database,
    discover_csv_files,
    export_dataset,
    import_csv_files,
    table_counts,
)
from app.database.validation import validate_raw_rows

ACCOUNTS_HEADER = "account_id,company_name,owner_email,plan,status,product_version,created_at"
ACCOUNT_ROWS = [
    "A9001,Judge Test Co,judge.one@example.com,Pro,active,4.3,2026-01-10",
    "A9002,Judge Second Co,judge.two@example.com,Business,past_due,4.2,2025-06-01",
]
INVOICES_HEADER = "invoice_id,account_id,amount,currency,charged_on,status,failure_reason,card_last4"


def write(dir_: Path, table: str, header: str, rows: list[str]) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"{table}.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def judge_dir(tmp_path: Path) -> Path:
    d = tmp_path / "test_accounts"
    write(d, "accounts", ACCOUNTS_HEADER, ACCOUNT_ROWS)
    write(d, "invoices", INVOICES_HEADER, [
        "INV-J001,A9001,49.0,USD,2026-09-22,paid,,4242",
        "INV-J002,A9002,299.0,USD,2026-10-01,failed,card_declined,1111",
    ])
    write(d, "usage", "account_id,period,workflow_runs,api_calls_peak_per_min,seats_used", ["A9001,2026-10,20000,600,10"])
    return d


def load(db, directory: Path, **kwargs):
    files, _ = discover_csv_files([directory])
    return import_csv_files(db.engine, files, **kwargs)


# --- happy path ----------------------------------------------------------------
def test_judge_reserved_ids_load(db, tmp_path) -> None:
    report = load(db, judge_dir(tmp_path))
    assert report.committed and report.ok
    counts = table_counts(db.engine)
    assert (counts["accounts"], counts["invoices"], counts["usage"]) == (2, 2, 1)


def test_repeatable_import_is_a_no_op(db, tmp_path) -> None:
    d = judge_dir(tmp_path)
    load(db, d)
    second = load(db, d)
    assert second.committed
    assert second.tables["accounts"].unchanged == 2 and second.tables["accounts"].inserted == 0
    assert table_counts(db.engine)["accounts"] == 2


def test_round_trip_export_import_export(db, tmp_path, seeded_data, reference_data) -> None:
    plan_limits, rules = reference_data
    raw = dict(seeded_data.rows, plan_limits=[p.model_dump() for p in plan_limits.values()], policy_registry=[r.model_dump() for r in rules])
    dataset, issues = validate_raw_rows(raw)
    assert not issues
    first = tmp_path / "export1"
    files = export_dataset(dataset, first)
    report = import_csv_files(db.engine, files)
    assert report.committed, [i.to_dict() for i in report.issues]
    assert table_counts(db.engine) == {t: len(rows) for t, rows in dataset.items()} | {"handoffs": 0}

    second = tmp_path / "export2"
    export_dataset({t: v for t, v in dataset_from_database(db.engine).items() if t in dataset}, second)
    for path in files.values():
        assert path.read_bytes() == (second / path.name).read_bytes(), path.name


def test_headers_matched_by_name_case_and_order_insensitive(db, tmp_path) -> None:
    d = tmp_path / "shuffled"
    write(d, "accounts", "Status, PLAN ,account_id,created_at,product_version,owner_email,company_name,notes",
          ["active,pro,A1001,2026-01-05,4.3,x.y@example.com,Aster Labs,extra column is fine"])
    report = load(db, d)
    assert report.committed
    assert any(i.code == "extra_column" and i.severity == "warning" for i in report.issues)
    account = dataset_from_database(db.engine)["accounts"][0]
    assert account.plan == "Pro" and account.status == "active"  # normalised to Annex C spelling


# --- malformed input -------------------------------------------------------------
def test_missing_required_column_rejects_file(db, tmp_path) -> None:
    d = tmp_path / "bad"
    write(d, "accounts", "account_id,company_name,plan,status,product_version,created_at", ["A1001,X,Pro,active,4.3,2026-01-01"])
    report = load(db, d)
    assert not report.committed
    assert any("owner_email" in i.message for i in report.issues)


@pytest.mark.parametrize(
    ("row", "column"),
    [
        ("INV-1,A9001,-49.0,USD,2026-09-22,paid,,4242", "amount"),
        ("INV-1,A9001,49.0,USD,2026-02-30,paid,,4242", "charged_on"),
        ("INV-1,A9001,49.0,USD,2026-09-22,paid,,4111111111111111", "card_last4"),
        ("INV-1,A9001,49.0,USD,2026-09-22,paid,card_declined,4242", None),
        ("INV-1,A9001,49.0,USD,2026-09-22,maybe,,4242", "status"),
    ],
)
def test_malformed_rows_reported_with_row_numbers_and_rolled_back(db, tmp_path, row, column) -> None:
    d = judge_dir(tmp_path)
    write(d, "invoices", INVOICES_HEADER, ["INV-J001,A9001,49.0,USD,2026-09-22,paid,,4242", row])
    report = load(db, d)
    assert not report.committed
    errors = [i for i in report.issues if i.severity == "error"]
    assert errors and errors[0].row == 2 and errors[0].table == "invoices"
    if column:
        assert errors[0].column == column
    assert table_counts(db.engine)["accounts"] == 0  # whole import rolled back
    assert "4111111111111111" not in json.dumps(report.to_dict())  # value never echoed


def test_wrong_field_count_is_malformed_row(db, tmp_path) -> None:
    d = tmp_path / "short"
    write(d, "accounts", ACCOUNTS_HEADER, ["A1001,Only three,fields"])
    report = load(db, d)
    assert not report.committed and report.issues[0].code == "malformed_row"


@pytest.mark.parametrize(
    "content",
    [b"\xff\xfe\x00garbage", b"account_id,company_name\x00\n", b"", b'account_id,company_name,owner_email,plan,status,product_version,created_at\n"A1001,unterminated\n'],
)
def test_corrupt_files_are_reported_not_crashing(db, tmp_path, content) -> None:
    d = tmp_path / "corrupt"
    d.mkdir()
    (d / "accounts.csv").write_bytes(content)
    report = load(db, d)
    assert not report.committed
    assert any(i.severity == "error" for i in report.issues)


def test_oversized_file_rejected(db, tmp_path, monkeypatch) -> None:
    import app.database.csv_io as csv_io

    monkeypatch.setattr(csv_io, "MAX_CSV_BYTES", 50)
    report = load(db, judge_dir(tmp_path))
    assert not report.committed and any("limit" in i.message for i in report.issues)


def test_validation_errors_do_not_echo_pii(db, tmp_path) -> None:
    d = tmp_path / "pii"
    write(d, "accounts", ACCOUNTS_HEADER, ["A1001,X,real.person@gmail.com,Pro,active,4.3,2026-01-01"])
    report = load(db, d)
    assert not report.committed
    assert "real.person@gmail.com" not in json.dumps(report.to_dict())


# --- referential integrity & duplicates -------------------------------------------
def test_invalid_foreign_key_rejected_and_rolled_back(db, tmp_path) -> None:
    d = judge_dir(tmp_path)
    write(d, "invoices", INVOICES_HEADER, ["INV-J001,A9001,49.0,USD,2026-09-22,paid,,4242", "INV-J009,A9999,49.0,USD,2026-09-22,paid,,4242"])
    report = load(db, d)
    assert not report.committed
    fk = [i for i in report.issues if i.code == "foreign_key"]
    assert fk and fk[0].key == "INV-J009"
    assert table_counts(db.engine)["accounts"] == 0


def test_skip_invalid_commits_valid_rows_and_rejects_dependants(db, tmp_path) -> None:
    d = judge_dir(tmp_path)
    write(d, "accounts", ACCOUNTS_HEADER, [ACCOUNT_ROWS[0], "A9002,Bad Email Co,x@gmail.com,Business,past_due,4.2,2025-06-01"])
    report = load(db, d, skip_invalid=True)
    assert report.committed
    counts = table_counts(db.engine)
    assert counts["accounts"] == 1  # A9002 rejected
    assert counts["invoices"] == 1  # A9002's invoice rejected as a dependant (FK)
    assert report.tables["invoices"].rejected == 1


def test_duplicate_ids_within_file_rejected(db, tmp_path) -> None:
    d = tmp_path / "dup"
    write(d, "accounts", ACCOUNTS_HEADER, [ACCOUNT_ROWS[0], ACCOUNT_ROWS[0].replace("Judge Test Co", "Other Name")])
    report = load(db, d)
    assert not report.committed
    assert any(i.code == "duplicate_key" and i.row == 2 for i in report.issues)


# --- conflicts with existing records ----------------------------------------------
def _conflicting_dir(tmp_path: Path) -> Path:
    d = tmp_path / "changed"
    write(d, "accounts", ACCOUNTS_HEADER, [ACCOUNT_ROWS[0].replace(",active,", ",suspended,")])
    return d


def test_conflict_default_errors_without_overwriting(db, tmp_path) -> None:
    load(db, judge_dir(tmp_path))
    report = load(db, _conflicting_dir(tmp_path))
    assert not report.committed and any(i.code == "conflict" for i in report.issues)
    assert dataset_from_database(db.engine)["accounts"][0].status == "active"


def test_conflict_skip_keeps_existing(db, tmp_path) -> None:
    load(db, judge_dir(tmp_path))
    report = load(db, _conflicting_dir(tmp_path), conflict=ConflictPolicy.SKIP)
    assert report.committed and report.tables["accounts"].skipped == 1
    assert {a.account_id: a.status for a in dataset_from_database(db.engine)["accounts"]}["A9001"] == "active"


def test_overwrite_requires_explicit_permission(db, tmp_path) -> None:
    load(db, judge_dir(tmp_path))
    with pytest.raises(ValueError, match="allow_overwrite"):
        load(db, _conflicting_dir(tmp_path), conflict=ConflictPolicy.OVERWRITE)
    report = load(db, _conflicting_dir(tmp_path), conflict=ConflictPolicy.OVERWRITE, allow_overwrite=True)
    assert report.committed and report.tables["accounts"].updated == 1
    assert {a.account_id: a.status for a in dataset_from_database(db.engine)["accounts"]}["A9001"] == "suspended"


def test_dry_run_commits_nothing(db, tmp_path) -> None:
    report = load(db, judge_dir(tmp_path), dry_run=True)
    assert not report.committed and report.ok
    assert table_counts(db.engine)["accounts"] == 0


def test_export_refuses_to_overwrite(tmp_path, seeded_data) -> None:
    dataset, _ = validate_raw_rows({"accounts": seeded_data.rows["accounts"]})
    export_dataset(dataset, tmp_path)
    with pytest.raises(FileExistsError):
        export_dataset(dataset, tmp_path)


def test_unrecognised_files_are_reported(tmp_path) -> None:
    d = judge_dir(tmp_path)
    (d / "customers.csv").write_text("a,b\n", encoding="utf-8")
    files, issues = discover_csv_files([d])
    assert set(files) == {"accounts", "invoices", "usage"}
    assert any(i.code == "unrecognised_file" for i in issues)


# --- consistency warnings & privacy in logs ---------------------------------------
def test_business_rules_are_warnings_for_judge_data(db, tmp_path) -> None:
    from datetime import date

    d = tmp_path / "inconsistent"
    write(d, "accounts", ACCOUNTS_HEADER, ["A9003,Odd Co,odd@example.com,Pro,past_due,4.3,2026-01-01"])
    write(d, "invoices", INVOICES_HEADER, ["INV-J010,A9003,49.0,USD,2026-10-01,paid,,4242"])
    report = load(db, d, reference_date=date(2026, 10, 6))
    assert report.committed  # never blocked by our interpretation
    assert any(i.code == "status_vs_invoices" and i.severity == "warning" for i in report.issues)


def test_loader_logs_contain_no_customer_data(db, tmp_path, log_output) -> None:
    load(db, judge_dir(tmp_path))
    output = log_output.getvalue()
    assert "csv_import_finished" in output
    for secret in ("judge.one@example.com", "Judge Test Co"):
        assert secret not in output
