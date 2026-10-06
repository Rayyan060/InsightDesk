"""CSV export and the judge-compatible CSV loader (Annex C schema).

Loader guarantees:

* **Headers by name.** Columns are matched by header name (case-insensitive,
  whitespace-trimmed), never by position. Missing required columns are a
  file-level error. Extra columns are allowed, because the guide permits
  added columns; they are reported as warnings and ignored.
* **Validation.** Every row goes through the Annex C row model
  (``app.database.row_schemas``). Malformed rows are reported with their CSV
  line number and column, and never with the offending value.
* **Referential integrity.** ``usage`` and ``invoices`` rows must reference an
  account that already exists or is part of the same import.
* **Transactions.** By default the whole import is one transaction: any error
  rolls everything back. ``skip_invalid=True`` instead commits the valid rows
  and reports the rejected ones (including dependants of rejected accounts).
* **Duplicates and repeatability.**
  * Duplicate keys within a file are rejected.
  * A row identical to an existing record is reported as ``unchanged``, so
    re-running the same import is a no-op.
  * A row that differs from an existing record follows the conflict policy:
    ``error`` (default) or ``skip``. ``overwrite`` updates the record, and only
    when explicitly allowed.
* **No reserved-ID filtering.** Judges load their own accounts in the
  reserved ranges (A9000–A9999, INV-J…). Those are rejected only by the
  synthetic-data validator, never here.
* **Safe parsing.** Size and row limits, undecodable bytes, NUL bytes and
  broken quoting become reported errors, not crashes.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine, select

from app.database.models import MANDATORY_TABLES, MODELS_BY_TABLE
from app.database.row_schemas import PRIMARY_KEYS, ROW_MODELS, all_columns, required_columns
from app.database.validation import (
    Dataset,
    Issue,
    check_business_rules,
    has_errors,
    primary_key,
    summarize,
    validation_issues,
)

logger = logging.getLogger(__name__)

MAX_CSV_BYTES = 20 * 1024 * 1024
MAX_CSV_ROWS = 200_000


class ConflictPolicy(str, Enum):
    ERROR = "error"
    SKIP = "skip"
    OVERWRITE = "overwrite"


class ImportAborted(Exception):
    """Raised internally to roll back an atomic import."""


@dataclass
class TableResult:
    table: str
    source: str
    rows_read: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    rejected: int = 0


@dataclass
class ImportReport:
    tables: dict[str, TableResult] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    committed: bool = False
    dry_run: bool = False
    conflict_policy: str = ConflictPolicy.ERROR.value
    skip_invalid: bool = False

    @property
    def ok(self) -> bool:
        return not has_errors(self.issues) or (self.skip_invalid and self.committed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "committed": self.committed,
            "dry_run": self.dry_run,
            "conflict_policy": self.conflict_policy,
            "skip_invalid": self.skip_invalid,
            "summary": summarize(self.issues),
            "tables": {name: vars(result) for name, result in self.tables.items()},
            "issues": [issue.to_dict() for issue in self.issues],
        }


# ---------------------------------------------------------------------- #
# Reading
# ---------------------------------------------------------------------- #
def _file_error(table: str, message: str, row: int | None = None) -> Issue:
    return Issue("error", "malformed_file", table, message, row=row)


def read_csv(path: Path, table: str) -> tuple[list[tuple[int, dict[str, str | None]]], list[Issue]]:
    """Read one CSV into ``(row_number, {column: value})`` pairs keyed by header name."""
    issues: list[Issue] = []
    try:
        size = path.stat().st_size
    except OSError:
        return [], [_file_error(table, f"cannot read file {path.name}")]
    if size > MAX_CSV_BYTES:
        return [], [_file_error(table, f"{path.name} exceeds the {MAX_CSV_BYTES}-byte limit")]

    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [_file_error(table, f"{path.name} is not valid UTF-8")]
    if "\x00" in text:
        return [], [_file_error(table, f"{path.name} contains NUL bytes")]

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header_raw = next(reader)
    except StopIteration:
        return [], [_file_error(table, f"{path.name} is empty")]
    except csv.Error:
        return [], [_file_error(table, f"{path.name} has a malformed header row")]

    header = [h.strip().lower() for h in header_raw]
    if len(set(header)) != len(header):
        return [], [_file_error(table, f"{path.name} has duplicate column names")]
    missing = [col for col in required_columns(table) if col not in header]
    if missing:
        return [], [_file_error(table, f"{path.name} is missing required columns: {', '.join(missing)}")]
    known = set(all_columns(table))
    for extra in (h for h in header if h not in known):
        issues.append(Issue("warning", "extra_column", table, "column is not part of the Annex C schema and was ignored", column=extra or "<blank>"))

    rows: list[tuple[int, dict[str, str | None]]] = []
    row_number = 0
    try:
        for values in reader:
            row_number += 1
            if not values or all(not v.strip() for v in values):
                continue  # blank line
            if row_number > MAX_CSV_ROWS:
                issues.append(_file_error(table, f"{path.name} exceeds the {MAX_CSV_ROWS}-row limit"))
                break
            if len(values) != len(header):
                issues.append(
                    Issue("error", "malformed_row", table, f"row has {len(values)} fields, header has {len(header)}", row=row_number)
                )
                continue
            record = {col: val for col, val in zip(header, values) if col in known}
            rows.append((row_number, record))
    except csv.Error:
        issues.append(_file_error(table, f"{path.name} has malformed CSV quoting", row=row_number + 1))
    return rows, issues


def parse_rows(table: str, rows: list[tuple[int, dict[str, Any]]]) -> tuple[list[tuple[int, BaseModel]], list[Issue]]:
    model = ROW_MODELS[table]
    parsed: list[tuple[int, BaseModel]] = []
    issues: list[Issue] = []
    seen: dict[str, int] = {}
    for row_number, values in rows:
        try:
            row = model.model_validate(values)
        except ValidationError as exc:
            issues.extend(validation_issues(table, exc, row_number, None))
            continue
        key = primary_key(table, row)
        if key in seen:
            issues.append(
                Issue("error", "duplicate_key", table, f"duplicate primary key (first seen on row {seen[key]})", row=row_number, key=key)
            )
            continue
        seen[key] = row_number
        parsed.append((row_number, row))
    return parsed, issues


def discover_csv_files(directories: Iterable[Path]) -> tuple[dict[str, Path], list[Issue]]:
    """Map ``<table>.csv`` files in the given directories to Annex C tables."""
    found: dict[str, Path] = {}
    issues: list[Issue] = []
    for directory in directories:
        if not directory.is_dir():
            issues.append(_file_error("-", f"directory not found: {directory}"))
            continue
        for path in sorted(directory.glob("*.csv")):
            table = path.stem.strip().lower()
            if table not in ROW_MODELS:
                issues.append(Issue("warning", "unrecognised_file", "-", f"{path.name} does not match an Annex C table name and was ignored"))
                continue
            if table in found:
                issues.append(_file_error(table, f"{table}.csv found in more than one directory"))
                continue
            found[table] = path
    return found, issues


# ---------------------------------------------------------------------- #
# Writing to SQLite
# ---------------------------------------------------------------------- #
def _row_values(row: BaseModel) -> dict[str, Any]:
    return row.model_dump()


def _same(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> bool:
    for column, value in incoming.items():
        current = existing.get(column)
        if isinstance(value, float) or isinstance(current, float):
            if current is None or value is None or float(current) != float(value):
                return False
        elif current != value:
            return False
    return True


def import_csv_files(
    engine: Engine,
    files: Mapping[str, Path],
    *,
    conflict: ConflictPolicy = ConflictPolicy.ERROR,
    allow_overwrite: bool = False,
    skip_invalid: bool = False,
    dry_run: bool = False,
    reference_date: date | None = None,
) -> ImportReport:
    """Validate and load CSV files into the Annex C tables.

    ``files`` maps table names to CSV paths; tables are processed in
    dependency order regardless of the mapping order.
    """
    if conflict is ConflictPolicy.OVERWRITE and not allow_overwrite:
        raise ValueError("overwrite requires allow_overwrite=True (explicit permission)")

    report = ImportReport(conflict_policy=conflict.value, skip_invalid=skip_invalid, dry_run=dry_run)
    parsed_by_table: dict[str, list[tuple[int, BaseModel]]] = {}

    for table in MANDATORY_TABLES:
        path = files.get(table)
        if path is None:
            continue
        result = TableResult(table=table, source=path.name)
        report.tables[table] = result
        raw_rows, read_issues = read_csv(path, table)
        result.rows_read = len(raw_rows)
        parsed, parse_issues = parse_rows(table, raw_rows)
        report.issues.extend(read_issues + parse_issues)
        result.rejected += len(raw_rows) - len(parsed)
        parsed_by_table[table] = parsed

    file_level_error = any(i.code in {"malformed_file"} for i in report.issues)
    if (has_errors(report.issues) and not skip_invalid) or file_level_error:
        logger.info("csv_import_rejected", extra={"error_count": summarize(report.issues)["error"]})
        return report

    try:
        with engine.begin() as conn:
            accepted_accounts: set[str] = set(
                conn.execute(select(MODELS_BY_TABLE["accounts"].account_id)).scalars()
            )
            for table in MANDATORY_TABLES:
                if table not in parsed_by_table:
                    continue
                result = report.tables[table]
                model = MODELS_BY_TABLE[table]
                pk_columns = PRIMARY_KEYS[table]
                for row_number, row in parsed_by_table[table]:
                    values = _row_values(row)
                    key = primary_key(table, row)

                    if table in ("usage", "invoices") and values["account_id"] not in accepted_accounts:
                        report.issues.append(
                            Issue("error", "foreign_key", table, "account_id references an account that does not exist", row=row_number, key=key, column="account_id")
                        )
                        result.rejected += 1
                        continue

                    where = [getattr(model, col) == values[col] for col in pk_columns]
                    existing = conn.execute(select(model.__table__).where(*where)).mappings().first()
                    if existing is None:
                        conn.execute(model.__table__.insert().values(**values))
                        result.inserted += 1
                    elif _same(existing, values):
                        result.unchanged += 1
                    elif conflict is ConflictPolicy.OVERWRITE:
                        conn.execute(model.__table__.update().where(*where).values(**values))
                        result.updated += 1
                    elif conflict is ConflictPolicy.SKIP:
                        report.issues.append(
                            Issue("warning", "conflict_skipped", table, "a different record with this key already exists; kept the existing record", row=row_number, key=key)
                        )
                        result.skipped += 1
                    else:
                        report.issues.append(
                            Issue("error", "conflict", table, "a different record with this key already exists (use --on-conflict skip, or overwrite with --allow-overwrite)", row=row_number, key=key)
                        )
                        result.rejected += 1
                        continue

                    if table == "accounts":
                        accepted_accounts.add(values["account_id"])

            if has_errors(report.issues) and not skip_invalid:
                raise ImportAborted
            if dry_run:
                raise ImportAborted
    except ImportAborted:
        report.committed = False
    else:
        report.committed = True

    if report.committed and reference_date is not None:
        report.issues.extend(_post_import_warnings(engine, parsed_by_table, reference_date))
    logger.info(
        "csv_import_finished",
        extra={"committed": report.committed, **{f"{k}_count": v for k, v in summarize(report.issues).items()}},
    )
    return report


def _post_import_warnings(
    engine: Engine, parsed_by_table: dict[str, list[tuple[int, BaseModel]]], reference_date: date
) -> list[Issue]:
    """Business-consistency checks on imported accounts, reported as warnings only."""
    touched = {row.account_id for _, row in parsed_by_table.get("accounts", [])}
    touched |= {row.account_id for t in ("usage", "invoices") for _, row in parsed_by_table.get(t, [])}
    if not touched:
        return []
    dataset = dataset_from_database(engine)
    scoped: Dataset = {
        "accounts": [a for a in dataset["accounts"] if a.account_id in touched],
        "usage": [u for u in dataset["usage"] if u.account_id in touched],
        "invoices": [i for i in dataset["invoices"] if i.account_id in touched],
    }
    return [
        issue
        for issue in check_business_rules(scoped, reference_date=reference_date, severity="warning")
        if issue.table in {"accounts", "usage", "invoices"}
    ]


# ---------------------------------------------------------------------- #
# Export
# ---------------------------------------------------------------------- #
def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def sort_rows(table: str, rows: Iterable[BaseModel]) -> list[BaseModel]:
    return sorted(rows, key=lambda r: tuple(str(getattr(r, c)) for c in PRIMARY_KEYS[table]))


def write_table_csv(path: Path, table: str, rows: Iterable[BaseModel], *, overwrite: bool = False) -> int:
    """Write rows in Annex C column order, sorted by primary key (deterministic)."""
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists (pass overwrite=True / --force to replace it)")
    columns = all_columns(table)
    ordered = sort_rows(table, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in ordered:
            writer.writerow([_format(getattr(row, c)) for c in columns])
    return len(ordered)


def export_dataset(dataset: Dataset, directory: Path, *, overwrite: bool = False) -> dict[str, Path]:
    if not overwrite:
        clashes = [directory / f"{t}.csv" for t in dataset if (directory / f"{t}.csv").exists()]
        if clashes:
            raise FileExistsError(f"refusing to overwrite existing files: {', '.join(p.name for p in clashes)}")
    written = {}
    for table in MANDATORY_TABLES:
        if table in dataset:
            path = directory / f"{table}.csv"
            write_table_csv(path, table, dataset[table], overwrite=overwrite)
            written[table] = path
    return written


def dataset_from_database(engine: Engine, tables: Iterable[str] = MANDATORY_TABLES) -> Dataset:
    dataset: Dataset = {}
    with engine.connect() as conn:
        for table in tables:
            model = MODELS_BY_TABLE[table]
            rows = conn.execute(select(model.__table__)).mappings().all()
            dataset[table] = [ROW_MODELS[table].model_validate(dict(r)) for r in rows]
    return dataset


def export_database(engine: Engine, directory: Path, *, overwrite: bool = False, tables: Iterable[str] = MANDATORY_TABLES) -> dict[str, Path]:
    return export_dataset(dataset_from_database(engine, tables), directory, overwrite=overwrite)


def table_counts(engine: Engine) -> dict[str, int]:
    from sqlalchemy import func

    counts = {}
    with engine.connect() as conn:
        for table in MANDATORY_TABLES:
            model = MODELS_BY_TABLE[table]
            counts[table] = conn.execute(select(func.count()).select_from(model.__table__)).scalar_one()
    return counts
