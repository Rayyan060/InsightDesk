"""Judge-compatible test-data loader (guide Section 4.2 / Section 6).

    python scripts/load_accounts.py --dir test_accounts/

Loads every ``<table>.csv`` found in the given directories (Annex C table
names: accounts, usage, invoices, plan_limits, platform_status,
policy_registry, handoffs) into the application database. The schema is
created first if missing. See ``app.database.csv_io`` for the guarantees.

Exit codes: 0 loaded (or dry run passed), 1 rejected or rolled back, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.cli.common import out, parse_date, project_path, resolve_db_url, setup_logging
from app.database.connection import Database
from app.database.csv_io import ConflictPolicy, discover_csv_files, import_csv_files, table_counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="load_accounts", description="Load Annex C CSV files into SQLite.")
    parser.add_argument("--dir", action="append", required=True, type=project_path, help="directory containing <table>.csv files (repeatable)")
    parser.add_argument("--db", help="SQLite file path or sqlite:/// URL (default: DATABASE_URL)")
    parser.add_argument("--on-conflict", choices=[c.value for c in ConflictPolicy], default="error",
                        help="what to do when a different record with the same key exists (default: error)")
    parser.add_argument("--allow-overwrite", action="store_true", help="required together with --on-conflict overwrite")
    parser.add_argument("--skip-invalid", action="store_true", help="commit valid rows and report invalid ones instead of rolling back")
    parser.add_argument("--dry-run", action="store_true", help="validate and simulate the import, then roll back")
    parser.add_argument("--reference-date", type=parse_date, default=None, help="date for consistency warnings (default: today)")
    parser.add_argument("--report", type=project_path, help="write the full JSON report to this path")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    conflict = ConflictPolicy(args.on_conflict)
    if conflict is ConflictPolicy.OVERWRITE and not args.allow_overwrite:
        parser.error("--on-conflict overwrite requires --allow-overwrite (explicit permission to replace existing records)")

    files, discovery_issues = discover_csv_files(args.dir)
    for issue in discovery_issues:
        out(f"{issue.severity.upper()}: {issue.message}")
    if any(i.severity == "error" for i in discovery_issues):
        return 1
    if not files:
        out("No Annex C CSV files found (expected names like accounts.csv, usage.csv, invoices.csv).")
        return 1

    database = Database(resolve_db_url(args.db))
    try:
        database.init_schema()
        report = import_csv_files(
            database.engine,
            files,
            conflict=conflict,
            allow_overwrite=args.allow_overwrite,
            skip_invalid=args.skip_invalid,
            dry_run=args.dry_run,
            reference_date=args.reference_date or date.today(),
        )
        counts = table_counts(database.engine)
    finally:
        database.dispose()

    out(f"{'DRY RUN - ' if args.dry_run else ''}{'COMMITTED' if report.committed else 'NOT COMMITTED (rolled back)'}")
    out(f"{'table':<16}{'read':>6}{'inserted':>10}{'updated':>9}{'unchanged':>11}{'skipped':>9}{'rejected':>10}")
    for name, r in report.tables.items():
        out(f"{name:<16}{r.rows_read:>6}{r.inserted:>10}{r.updated:>9}{r.unchanged:>11}{r.skipped:>9}{r.rejected:>10}")
    errors = [i for i in report.issues if i.severity == "error"]
    warnings = [i for i in report.issues if i.severity == "warning"]
    for issue in errors[:50] + warnings[:50]:
        where = f"{issue.table}" + (f" row {issue.row}" if issue.row else "") + (f" [{issue.key}]" if issue.key else "") + (f" {issue.column}" if issue.column else "")
        out(f"  {issue.severity.upper():<8}{where}: {issue.message}")
    if len(errors) > 50 or len(warnings) > 50:
        out(f"  ... {len(errors)} errors and {len(warnings)} warnings in total (see --report)")
    out("Database row counts: " + ", ".join(f"{t}={n}" for t, n in counts.items()))

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    if args.dry_run:
        return 0 if not errors else 1
    return 0 if report.committed else 1


if __name__ == "__main__":
    raise SystemExit(main())
