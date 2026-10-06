"""Validate the knowledge base and Source Register; exit 1 on any error.

    python scripts/validate_knowledge.py
    python scripts/validate_knowledge.py --reference-date 2026-11-15 --no-report

Writes data/source_register/knowledge_validation_report.md/.json unless --no-report.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from app.cli.common import out, parse_date, setup_logging
from app.knowledge.catalog import REFERENCE_DATE
from app.knowledge.documents import DATA_DIR, REGISTER_DIR
from app.knowledge.validation import render_report_markdown, validate_knowledge


def run_validation(reference: date, *, write_report: bool) -> int:
    report = validate_knowledge(DATA_DIR, reference_date=reference)
    if write_report:
        REGISTER_DIR.mkdir(parents=True, exist_ok=True)
        (REGISTER_DIR / "knowledge_validation_report.md").write_text(render_report_markdown(report, reference_date=reference), encoding="utf-8")
        (REGISTER_DIR / "knowledge_validation_report.json").write_text(
            json.dumps({"ok": report.ok, "reference_date": reference.isoformat(), "counts": report.counts,
                        "issues": [i.to_dict() for i in report.issues]}, indent=2) + "\n",
            encoding="utf-8",
        )
    c = report.counts
    out(f"Sources: {c['total']} (articles {c['article']}, policies {c['policy']}, release notes {c['release_note']}, "
        f"tickets {c['ticket']}, community {c['community']})")
    for issue in report.errors[:60]:
        out(f"  ERROR {issue.code} [{issue.source_id or '-'}] {issue.message}")
    for issue in report.warnings[:30]:
        out(f"  WARN  {issue.code} [{issue.source_id or '-'}] {issue.message}")
    out(f"{'PASS' if report.ok else 'FAIL'}: {len(report.errors)} errors, {len(report.warnings)} warnings")
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="validate_knowledge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reference-date", type=parse_date, default=date.fromisoformat(REFERENCE_DATE))
    p.add_argument("--no-report", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    setup_logging(args.verbose)
    return run_validation(args.reference_date, write_report=not args.no_report)


if __name__ == "__main__":
    raise SystemExit(main())
