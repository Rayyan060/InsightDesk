"""Deterministic data pipeline.

    Generate → Validate schema → Validate business constraints → Export CSV
             → Import into SQLite → Verify row counts → Validation report

The import step uses a throwaway SQLite file in a temporary directory, so the
pipeline never touches the application database. Loading into the app
database is a separate, explicit step (``load_accounts`` / ``init_db``).
Existing CSVs are never overwritten unless ``force=True``.
"""

from __future__ import annotations

import csv
import json
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.core.config import PROJECT_ROOT
from app.database.connection import Database
from app.database.csv_io import (
    ConflictPolicy,
    export_dataset,
    import_csv_files,
    parse_rows,
    read_csv,
    table_counts,
)
from app.database.row_schemas import PlanLimitRow, PolicyRuleRow
from app.database.validation import (
    Dataset,
    Issue,
    check_business_rules,
    check_policy_registry_conflicts,
    check_referential,
    check_reserved_identifiers,
    has_errors,
    summarize,
    validate_raw_rows,
)
from app.synthetic.edge_cases import EdgeCaseResult, verify_edge_cases
from app.synthetic.generator import GeneratedData, generate_seeded

REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"
PROMPTS_DIR = SYNTHETIC_DIR / "prompts"
GENERATED_TABLES = ("accounts", "usage", "invoices", "platform_status")
REPORT_JSON = "validation_report.json"
REPORT_MD = "validation_report.md"
MANIFEST_CSV = "edge_cases.csv"
PROVENANCE_JSON = "generation_manifest.json"


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class PipelineResult:
    steps: list[StepResult] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    edge_cases: list[EdgeCaseResult] = field(default_factory=list)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    distributions: dict[str, Any] = field(default_factory=dict)
    llm_summary: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return all(step.ok for step in self.steps)


# ---------------------------------------------------------------------- #
# Reference data
# ---------------------------------------------------------------------- #
def load_reference(reference_dir: Path = REFERENCE_DIR) -> tuple[dict[str, PlanLimitRow], list[PolicyRuleRow], list[Issue]]:
    issues: list[Issue] = []
    tables: dict[str, list[Any]] = {}
    for table in ("plan_limits", "policy_registry"):
        raw, read_issues = read_csv(reference_dir / f"{table}.csv", table)
        parsed, parse_issues = parse_rows(table, raw)
        issues += read_issues + parse_issues
        tables[table] = [row for _, row in parsed]
    plan_limits = {row.plan: row for row in tables["plan_limits"]}
    return plan_limits, tables["policy_registry"], issues


SOURCE_REGISTER = PROJECT_ROOT / "data" / "source_register" / "source_register.csv"


def policy_source_ids(register: Path = SOURCE_REGISTER) -> set[str] | None:
    """Policy-article IDs from the Source Register (Phase 3), or None if it doesn't exist yet."""
    if not register.exists():
        return None
    with register.open(encoding="utf-8-sig", newline="") as handle:
        return {row["source_id"] for row in csv.DictReader(handle) if row.get("doc_type") == "policy"}


# ---------------------------------------------------------------------- #
# Validation shared by the pipeline and the validate CLI
# ---------------------------------------------------------------------- #
def validate_synthetic_dataset(
    dataset: Dataset,
    manifest: list[dict[str, str]],
    *,
    plan_limits: dict[str, PlanLimitRow],
    policy_rules: list[PolicyRuleRow],
    reference_date: date,
) -> tuple[list[Issue], list[EdgeCaseResult]]:
    """Strict validation of our own dataset: every violation is an error."""
    issues = check_referential(dataset)
    issues += check_reserved_identifiers(dataset)
    issues += check_business_rules(
        dataset, reference_date=reference_date, severity="error", known_source_ids=policy_source_ids()
    )
    issues += check_policy_registry_conflicts(dataset.get("policy_registry", []))
    edge = verify_edge_cases(dataset, manifest, plan_limits=plan_limits, policy_rules=policy_rules, reference_date=reference_date)
    for result in edge:
        if not result.passed:
            issues.append(Issue("error", "edge_case_missing", "accounts", f"{result.case}: {result.detail}"))
    return issues, edge


def distributions(dataset: Dataset) -> dict[str, Any]:
    accounts = dataset.get("accounts", [])
    by_plan_status: dict[str, dict[str, int]] = {}
    for a in accounts:
        by_plan_status.setdefault(a.plan, {}).setdefault(a.status, 0)
        by_plan_status[a.plan][a.status] += 1
    versions: dict[str, int] = {}
    for a in accounts:
        versions[a.product_version] = versions.get(a.product_version, 0) + 1
    invoice_status: dict[str, int] = {}
    currency: dict[str, int] = {}
    per_account: dict[str, int] = {}
    for inv in dataset.get("invoices", []):
        invoice_status[inv.status] = invoice_status.get(inv.status, 0) + 1
        currency[inv.currency] = currency.get(inv.currency, 0) + 1
        per_account[inv.account_id] = per_account.get(inv.account_id, 0) + 1
    invoice_count_hist: dict[str, int] = {}
    for a in accounts:
        n = str(per_account.get(a.account_id, 0))
        invoice_count_hist[n] = invoice_count_hist.get(n, 0) + 1
    return {
        "accounts_by_plan_and_status": by_plan_status,
        "accounts_by_product_version": dict(sorted(versions.items())),
        "invoices_by_status": invoice_status,
        "invoices_by_currency": currency,
        "accounts_by_invoice_count": dict(sorted(invoice_count_hist.items(), key=lambda kv: int(kv[0]))),
        "usage_rows_by_period": _count_by(dataset.get("usage", []), "period"),
        "platform_status": {r.component: r.status for r in dataset.get("platform_status", [])},
    }


def _count_by(rows: list[Any], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = getattr(row, attr)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------------- #
# Pipeline
# ---------------------------------------------------------------------- #
def run_pipeline(
    *,
    out_dir: Path = SYNTHETIC_DIR,
    reference_dir: Path = REFERENCE_DIR,
    generator: Literal["seeded", "llm"] = "seeded",
    seed: int,
    reference_date: date,
    account_count: int,
    force: bool = False,
    llm: Any = None,
    llm_options: dict[str, Any] | None = None,
) -> PipelineResult:
    result = PipelineResult()

    existing = [out_dir / f"{t}.csv" for t in GENERATED_TABLES if (out_dir / f"{t}.csv").exists()]
    if existing and not force:
        result.steps.append(
            StepResult("preflight", False, "refusing to overwrite existing CSVs: " + ", ".join(p.name for p in existing) + " (use --force)")
        )
        return result

    plan_limits, rules, ref_issues = load_reference(reference_dir)
    result.issues += ref_issues
    if has_errors(ref_issues):
        result.steps.append(StepResult("load_reference", False, "reference data is invalid"))
        return result

    # 1. Generate
    if generator == "seeded":
        generated: GeneratedData = generate_seeded(
            seed=seed, reference_date=reference_date, plan_limits=plan_limits, policy_rules=rules, account_count=account_count
        )
    else:
        from app.synthetic.llm_generator import generate_with_llm

        generated, summary = generate_with_llm(
            llm, seed=seed, reference_date=reference_date, plan_limits=plan_limits, policy_rules=rules,
            prompts_dir=PROMPTS_DIR, account_count=account_count, **(llm_options or {}),
        )
        result.llm_summary = summary.to_dict()
    result.provenance = {
        **generated.provenance,
        "account_count": account_count,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    result.steps.append(StepResult("generate", True, f"{generator} generator, {len(generated.rows['accounts'])} accounts"))

    # 2. Schema
    raw = dict(generated.rows)
    raw["plan_limits"] = [p.model_dump() for p in plan_limits.values()]
    raw["policy_registry"] = [r.model_dump() for r in rules]
    dataset, schema_issues = validate_raw_rows(raw)
    result.issues += schema_issues
    result.steps.append(StepResult("validate_schema", not has_errors(schema_issues), f"{summarize(schema_issues)['error']} schema errors"))
    if has_errors(schema_issues):
        return result

    # 3. Business constraints + edge cases
    business_issues, edge = validate_synthetic_dataset(
        dataset, generated.manifest, plan_limits=plan_limits, policy_rules=rules, reference_date=reference_date
    )
    result.issues += business_issues
    result.edge_cases = edge
    result.distributions = distributions(dataset)
    passed = sum(1 for e in edge if e.passed)
    result.steps.append(
        StepResult("validate_business", not has_errors(business_issues), f"{summarize(business_issues)['error']} errors; {passed}/{len(edge)} edge-case and coverage checks passed")
    )
    if has_errors(business_issues):
        return result

    # 4. Export CSV
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_only = {t: dataset[t] for t in GENERATED_TABLES}
    written = export_dataset(generated_only, out_dir, overwrite=force)
    _write_manifest(out_dir / MANIFEST_CSV, generated.manifest)
    result.steps.append(StepResult("export_csv", True, ", ".join(sorted(p.name for p in written.values()))))

    # 5. Import into a throwaway SQLite database
    with tempfile.TemporaryDirectory(prefix="insightdesk_pipeline_") as tmp:
        db = Database(f"sqlite:///{(Path(tmp) / 'staging.db').as_posix()}")
        try:
            db.init_schema()
            files = {t: reference_dir / f"{t}.csv" for t in ("plan_limits", "policy_registry")} | written
            report = import_csv_files(db.engine, files, conflict=ConflictPolicy.ERROR)
            result.issues += [i for i in report.issues if i.severity == "error"]
            result.steps.append(StepResult("import_sqlite", report.committed, f"committed={report.committed}"))
            if not report.committed:
                return result

            # 6. Verify row counts
            db_counts = table_counts(db.engine)
        finally:
            db.dispose()
    expected = {t: len(dataset[t]) for t in dataset}
    mismatches = {t: (expected[t], db_counts.get(t)) for t in expected if expected[t] != db_counts.get(t)}
    result.counts = {"expected": expected, "database": db_counts}
    result.steps.append(StepResult("verify_row_counts", not mismatches, "all match" if not mismatches else f"mismatch: {mismatches}"))

    # 7. Reports
    write_reports(out_dir, result)
    (out_dir / PROVENANCE_JSON).write_text(
        json.dumps({"provenance": result.provenance, "counts": expected, "llm": result.llm_summary}, indent=2) + "\n",
        encoding="utf-8",
    )
    result.steps.append(StepResult("write_report", True, f"{REPORT_MD}, {REPORT_JSON}"))
    write_reports(out_dir, result)  # rewrite including the final step
    return result


def _write_manifest(path: Path, manifest: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["scenario", "account_id", "invoice_ids", "description"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest)


def read_manifest(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ---------------------------------------------------------------------- #
# Reports
# ---------------------------------------------------------------------- #
def report_dict(result: PipelineResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "steps": [vars(s) for s in result.steps],
        "summary": summarize(result.issues),
        "issues": [i.to_dict() for i in result.issues],
        "edge_cases": [vars(e) for e in result.edge_cases],
        "counts": result.counts,
        "distributions": result.distributions,
        "provenance": result.provenance,
        "llm": result.llm_summary,
    }


def render_markdown(result: PipelineResult) -> str:
    lines = ["# Synthetic data validation report", ""]
    lines.append(f"**Result:** {'PASS' if result.ok else 'FAIL'}  ")
    prov = result.provenance
    if prov:
        lines.append(
            f"**Generator:** {prov.get('generator')}"
            + (f" (model {prov.get('model')}, temperature {prov.get('temperature')})" if prov.get("generator") == "llm" else "")
            + f"; seed {prov.get('seed')}; reference date {prov.get('reference_date')}"
        )
    lines += ["", "## Pipeline steps", "", "| Step | Result | Detail |", "|---|---|---|"]
    lines += [f"| {s.name} | {'ok' if s.ok else 'FAILED'} | {s.detail} |" for s in result.steps]
    counts = summarize(result.issues)
    plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"  # noqa: E731
    lines += ["", f"## Issues ({plural(counts['error'], 'error')}, {plural(counts['warning'], 'warning')})", ""]
    if result.issues:
        lines += ["| Severity | Code | Table | Key | Column | Message |", "|---|---|---|---|---|---|"]
        for i in result.issues:
            lines.append(f"| {i.severity} | {i.code} | {i.table} | {i.key or ''} | {i.column or ''} | {i.message} |")
    else:
        lines.append("None.")
    if result.edge_cases:
        lines += ["", "## Edge cases and coverage (verified from the data)", "", "| Check | Result | Manifest account | Satisfied by |", "|---|---|---|---|"]
        for e in result.edge_cases:
            sat = ", ".join(e.satisfied_by[:8]) + (" ..." if len(e.satisfied_by) > 8 else "")
            lines.append(f"| {e.case} | {'pass' if e.passed else 'FAIL: ' + e.detail} | {e.manifest_account or ''} | {sat} |")
    if result.counts:
        lines += ["", "## Row counts (CSV vs SQLite import)", "", "| Table | Expected | In database |", "|---|---|---|"]
        for table, n in result.counts["expected"].items():
            lines.append(f"| {table} | {n} | {result.counts['database'].get(table)} |")
    if result.distributions:
        lines += ["", "## Distributions", "", "```json", json.dumps(result.distributions, indent=2), "```"]
    if result.llm_summary:
        s = result.llm_summary
        lines += [
            "",
            "## LLM generation",
            "",
            f"Calls: {s['calls']}; prompt tokens: {s['prompt_tokens']}; completion tokens: {s['completion_tokens']}; "
            f"accepted first try: {s['accepted_first_try']}; after retry: {s['accepted_after_retry']}; "
            f"fell back to seeded: {', '.join(s['fell_back_to_seeded']) or 'none'}",
        ]
        rejected = [a for a in s["attempts"] if a["outcome"] != "accepted"]
        if rejected:
            lines += ["", "| Target | Attempt | Outcome | Problems |", "|---|---|---|---|"]
            for a in rejected:
                lines.append(f"| {a['target']} | {a['attempt']} | {a['outcome']} | {'; '.join(a['problems'][:5])} |")
    return "\n".join(lines) + "\n"


def write_reports(out_dir: Path, result: PipelineResult) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / REPORT_JSON).write_text(json.dumps(report_dict(result), indent=2, default=str) + "\n", encoding="utf-8")
    (out_dir / REPORT_MD).write_text(render_markdown(result), encoding="utf-8")
