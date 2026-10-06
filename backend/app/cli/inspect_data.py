"""Inspect the dataset in a database or a CSV directory.

    python scripts/inspect_data.py                         # application database
    python scripts/inspect_data.py --dir data/synthetic    # CSV files
    python scripts/inspect_data.py --account A1010         # one account's records (email masked)
    python scripts/inspect_data.py --export out_dir/       # export the database to Annex C CSVs

Owner emails are always masked in output.
"""

from __future__ import annotations

import argparse
import json

from app.cli.common import mask_email, out, project_path, resolve_db_url, setup_logging
from app.database.connection import Database
from app.database.csv_io import dataset_from_database, export_database, parse_rows, read_csv
from app.database.models import MANDATORY_TABLES
from app.synthetic.pipeline import distributions


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="inspect_data", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = p.add_mutually_exclusive_group()
    source.add_argument("--db", help="SQLite file path or sqlite:/// URL (default: DATABASE_URL)")
    source.add_argument("--dir", type=project_path, help="directory of Annex C CSV files")
    p.add_argument("--account", help="show one account's records")
    p.add_argument("--export", type=project_path, help="export the database tables to this directory as CSV")
    p.add_argument("--force", action="store_true", help="allow --export to overwrite existing files")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    setup_logging(args.verbose)

    if args.dir:
        dataset = {}
        for table in MANDATORY_TABLES:
            path = args.dir / f"{table}.csv"
            if path.exists():
                raw, _ = read_csv(path, table)
                dataset[table] = [row for _, row in parse_rows(table, raw)[0]]
            else:
                dataset[table] = []
    else:
        database = Database(resolve_db_url(args.db))
        try:
            dataset = dataset_from_database(database.engine)
            if args.export:
                written = export_database(database.engine, args.export, overwrite=args.force)
                out("Exported: " + ", ".join(str(p) for p in written.values()))
        finally:
            database.dispose()

    out("Row counts: " + ", ".join(f"{t}={len(dataset.get(t, []))}" for t in MANDATORY_TABLES))
    if args.account:
        accounts = [a for a in dataset.get("accounts", []) if a.account_id == args.account]
        if not accounts:
            out(f"No account {args.account}")
            return 1
        account = accounts[0].model_dump()
        account["owner_email"] = mask_email(account["owner_email"])
        out(json.dumps({"account": account}, indent=2))
        for table in ("usage", "invoices"):
            rows = [r.model_dump() for r in dataset.get(table, []) if r.account_id == args.account]
            out(f"{table}:")
            for row in rows:
                out("  " + json.dumps(row))
        return 0
    out(json.dumps(distributions(dataset), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
