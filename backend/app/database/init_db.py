"""Database initialisation: create the Annex C schema and load reference data.

Safe to run repeatedly:

* ``CREATE TABLE`` is only issued for tables that don't exist. Nothing is
  dropped or truncated, so existing data survives.
* Reference data (``plan_limits``, ``policy_registry``) is loaded with the
  ``skip`` conflict policy. Identical rows are left unchanged, and rows an
  operator has edited in the database are kept rather than overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.database.annex_c import verify_schema
from app.database.connection import Database
from app.database.csv_io import ConflictPolicy, ImportReport, discover_csv_files, import_csv_files

DEFAULT_REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"


@dataclass
class InitReport:
    schema_problems: list[str] = field(default_factory=list)
    reference_import: ImportReport | None = None

    @property
    def ok(self) -> bool:
        return not self.schema_problems and (self.reference_import is None or self.reference_import.ok)


def initialize_database(database: Database, *, reference_dir: Path | None = DEFAULT_REFERENCE_DIR) -> InitReport:
    database.init_schema()
    report = InitReport(schema_problems=verify_schema(database.engine))
    if report.schema_problems or reference_dir is None:
        return report
    files, issues = discover_csv_files([reference_dir])
    reference_tables = {t: p for t, p in files.items() if t in {"plan_limits", "policy_registry"}}
    report.reference_import = import_csv_files(database.engine, reference_tables, conflict=ConflictPolicy.SKIP)
    report.reference_import.issues[:0] = issues
    return report
