"""Create the Annex C schema and load reference data (idempotent).

    python scripts/init_db.py                     # schema + plan_limits + policy_registry
    python scripts/init_db.py --with-synthetic    # also load data/synthetic (skip existing records)

Never drops tables or deletes rows. Safe to run repeatedly.
"""

from __future__ import annotations

import argparse
from datetime import date

from app.cli.common import out, project_path, resolve_db_url, setup_logging
from app.database.connection import Database
from app.database.csv_io import ConflictPolicy, discover_csv_files, import_csv_files, table_counts
from app.database.init_db import DEFAULT_REFERENCE_DIR, initialize_database
from app.synthetic.pipeline import SYNTHETIC_DIR


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="init_db", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", help="SQLite file path or sqlite:/// URL (default: DATABASE_URL)")
    p.add_argument("--reference-dir", type=project_path, default=DEFAULT_REFERENCE_DIR)
    p.add_argument("--no-reference", action="store_true", help="create the schema only")
    p.add_argument("--with-synthetic", action="store_true", help="also load the synthetic dataset (existing records are kept)")
    p.add_argument("--synthetic-dir", type=project_path, default=SYNTHETIC_DIR)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    setup_logging(args.verbose)

    database = Database(resolve_db_url(args.db))
    try:
        report = initialize_database(database, reference_dir=None if args.no_reference else args.reference_dir)
        if report.schema_problems:
            out("Schema does not match Annex C:")
            for problem in report.schema_problems:
                out(f"  - {problem}")
            return 1
        out("Schema: matches Annex C (7 tables)")
        ok = report.ok
        if report.reference_import:
            for name, r in report.reference_import.tables.items():
                out(f"Reference {name}: inserted {r.inserted}, unchanged {r.unchanged}, kept existing {r.skipped}, rejected {r.rejected}")
        if args.with_synthetic:
            files, _ = discover_csv_files([args.synthetic_dir])
            files = {t: f for t, f in files.items() if t in {"accounts", "usage", "invoices", "platform_status"}}
            synthetic = import_csv_files(database.engine, files, conflict=ConflictPolicy.SKIP, reference_date=date.today())
            for name, r in synthetic.tables.items():
                out(f"Synthetic {name}: inserted {r.inserted}, unchanged {r.unchanged}, kept existing {r.skipped}, rejected {r.rejected}")
            for issue in [i for i in synthetic.issues if i.severity == "error"][:20]:
                out(f"  ERROR {issue.table} [{issue.key or issue.row or ''}]: {issue.message}")
            ok = ok and synthetic.committed
        out("Row counts: " + ", ".join(f"{t}={n}" for t, n in table_counts(database.engine).items()))
    finally:
        database.dispose()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
