"""Validate a directory of Annex C CSV files and write a validation report.

    python scripts/validate_data.py                      # our dataset (strict: every violation is an error)
    python scripts/validate_data.py --mode judge --dir test_accounts/

``synthetic`` mode (default) checks schema, referential integrity, business
constraints, reserved identifiers and every required edge case, and writes
``validation_report.md`` / ``.json`` into the directory. ``judge`` mode checks
schema and referential integrity as errors and business consistency as
warnings, and doesn't reject reserved identifiers.
"""

from __future__ import annotations

import argparse
from datetime import date

from app.cli.common import out, parse_date, project_path, setup_logging
from app.database.csv_io import parse_rows, read_csv
from app.database.validation import Issue, check_business_rules, check_referential, has_errors, summarize
from app.synthetic.pipeline import (
    MANIFEST_CSV,
    REFERENCE_DIR,
    SYNTHETIC_DIR,
    PipelineResult,
    StepResult,
    distributions,
    load_reference,
    read_manifest,
    validate_synthetic_dataset,
    write_reports,
)
from app.synthetic.scenarios import DEFAULT_REFERENCE_DATE


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="validate_data", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", type=project_path, default=SYNTHETIC_DIR)
    p.add_argument("--reference-dir", type=project_path, default=REFERENCE_DIR)
    p.add_argument("--mode", choices=["synthetic", "judge"], default="synthetic")
    p.add_argument("--reference-date", type=parse_date, default=None,
                   help=f"default: {DEFAULT_REFERENCE_DATE} in synthetic mode, today in judge mode")
    p.add_argument("--no-report", action="store_true", help="print only; do not write report files")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    reference_date: date = args.reference_date or (DEFAULT_REFERENCE_DATE if args.mode == "synthetic" else date.today())
    result = PipelineResult()

    plan_limits, rules, issues = load_reference(args.reference_dir)
    dataset: dict[str, list] = {"plan_limits": list(plan_limits.values()), "policy_registry": rules}
    for table in ("accounts", "usage", "invoices", "platform_status"):
        path = args.dir / f"{table}.csv"
        if not path.exists():
            if args.mode == "synthetic":
                issues.append(Issue("error", "missing_file", table, f"{path.name} not found"))
            dataset[table] = []
            continue
        raw, read_issues = read_csv(path, table)
        parsed, parse_issues = parse_rows(table, raw)
        issues += read_issues + parse_issues
        dataset[table] = [row for _, row in parsed]
    result.issues += issues
    result.steps.append(StepResult("validate_schema", not has_errors(issues), f"{summarize(issues)['error']} schema/file errors"))

    if args.mode == "synthetic":
        business, edge = validate_synthetic_dataset(
            dataset, read_manifest(args.dir / MANIFEST_CSV), plan_limits=plan_limits, policy_rules=rules, reference_date=reference_date
        )
        result.edge_cases = edge
    else:
        business = check_referential(dataset) + check_business_rules(dataset, reference_date=reference_date, severity="warning")
    result.issues += business
    result.distributions = distributions(dataset)
    result.provenance = {"validated_dir": str(args.dir), "mode": args.mode, "reference_date": reference_date.isoformat()}
    result.steps.append(StepResult("validate_business", not has_errors(business), f"{summarize(business)['error']} errors, {summarize(business)['warning']} warnings"))

    if args.mode == "synthetic" and not args.no_report:
        write_reports(args.dir, result)

    for step in result.steps:
        out(f"[{'ok' if step.ok else 'FAILED':>6}] {step.name}: {step.detail}")
    for issue in [i for i in result.issues if i.severity == "error"][:50]:
        out(f"  ERROR {issue.table} [{issue.key or issue.row or ''}] {issue.column or ''}: {issue.message}")
    for issue in [i for i in result.issues if i.severity == "warning"][:20]:
        out(f"  WARN  {issue.table} [{issue.key or issue.row or ''}] {issue.column or ''}: {issue.message}")
    for e in result.edge_cases:
        out(f"  edge case {e.case:<30} {'pass' if e.passed else 'FAIL'}  {e.manifest_account or ''}")
    out("PASS" if result.ok else "FAIL")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
