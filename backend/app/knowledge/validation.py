"""Knowledge-base validation (``python scripts/validate_knowledge.py``).

Errors make the script exit non-zero. Every check has a stable code:

| Code | Check |
|---|---|
| register_columns / missing_metadata / invalid_metadata | Annex B columns and values (doc_type, authority 1-5, dates, version grammar, Y/N) |
| duplicate_source_id | Unique source IDs |
| reserved_source_id | No ``JD-`` IDs (reserved for judges) |
| document_missing / orphan_document | Register entries without files, and files without entries |
| title_mismatch / missing_title / invalid_ticket | File content agrees with the register |
| empty_content / empty_section / duplicate_content | Usable, distinct content |
| authority_mismatch | authority_level equals the Annex A level for the doc_type |
| future_last_updated / impossible_dates / version_not_released | Date sanity, including a ticket's version existing on its resolved date |
| versions_cover_nothing | product_versions covers at least one shipped version |
| unknown_reference / supersedes_cycle / supersedes_newer | supersedes and conflicts_with point at real, older sources |
| policy_source_missing / policy_section_missing / policy_value_mismatch | Every registry rule cites a policy article and section that exists and states the value |
| plan_limits_mismatch | The KB-POL-002 table equals plan_limits.csv |
| minimum_* | Section 4.1 minimums (30 articles, 25 tickets, 3 angry, 3 outdated, 2 major versions, future deprecation, 6 policies) |
| injection_unlabelled / injection_undetected | The detector flags exactly the labelled adversarial fixtures |
| coverage_gap_mentioned | Deliberately uncovered topics stay uncovered |
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from app.knowledge.catalog import COVERAGE_GAPS
from app.knowledge.documents import DATA_DIR, DOC_DIRS, KnowledgeBase, load_knowledge_base
from app.knowledge.precedence import effective_date
from app.knowledge.safety import scan_for_instructions
from app.knowledge.versions import KNOWN_VERSIONS, RELEASE_DATES, parse_version_spec
from app.schemas.ingestion import AUTHORITY_BY_DOC_TYPE, DocType

POLICY_IDS = tuple(f"KB-POL-{n:03d}" for n in range(1, 7))
MINIMUMS = {"article": 30, "ticket": 25, "angry_complaint": 3, "outdated": 3}


@dataclass(frozen=True)
class KnowledgeIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str
    source_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class KnowledgeReport:
    issues: list[KnowledgeIssue]
    counts: dict[str, Any]

    @property
    def errors(self) -> list[KnowledgeIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[KnowledgeIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def read_labels(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row["source_id"]: {
                **row,
                "labels": [x for x in row.get("labels", "").split(";") if x],
                "conflicts_with": [x for x in row.get("conflicts_with", "").split(";") if x],
            }
            for row in csv.DictReader(handle)
        }


def _numbers(text: str) -> set[str]:
    return {m.replace(",", "") for m in re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", text)}


def _plan_table(text: str) -> dict[str, list[str]]:
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[0] in {"Free", "Pro", "Business", "Enterprise"}:
            rows[cells[0]] = [c.replace(",", "").replace("$", "") for c in cells[1:6]]
    return rows


def validate_knowledge(
    data_dir: Path = DATA_DIR,
    *,
    reference_date: date,
    kb: KnowledgeBase | None = None,
) -> KnowledgeReport:
    kb = kb or load_knowledge_base(data_dir)
    issues: list[KnowledgeIssue] = [KnowledgeIssue(i.severity, i.code, i.message, i.source_id) for i in kb.issues]
    add = lambda code, message, source_id=None, severity="error": issues.append(KnowledgeIssue(severity, code, message, source_id))  # noqa: E731
    labels = read_labels(data_dir / "source_register" / "kb_labels.csv")
    ids = [e.source_id for e in kb.entries]
    by_id = {e.source_id: e for e in kb.entries}

    # --- register-level ---------------------------------------------------
    for source_id, count in Counter(ids).items():
        if count > 1:
            add("duplicate_source_id", f"source_id appears {count} times", source_id)
    for entry in kb.entries:
        sid = entry.source_id
        if sid.upper().startswith("JD-"):
            add("reserved_source_id", "JD- source IDs are reserved for judges", sid)
        if entry.authority_level != AUTHORITY_BY_DOC_TYPE[entry.doc_type]:
            add("authority_mismatch", f"{entry.doc_type.value} must have authority_level {AUTHORITY_BY_DOC_TYPE[entry.doc_type]} (Annex A)", sid)
        if entry.last_updated > reference_date:
            add("future_last_updated", f"last_updated {entry.last_updated} is after the reference date", sid)
        if entry.effective_from and entry.deprecated_on and entry.deprecated_on <= entry.effective_from:
            add("impossible_dates", "deprecated_on is not after effective_from", sid)
        if not parse_version_spec(entry.product_versions).covered_known_versions():
            add("versions_cover_nothing", f"product_versions {entry.product_versions!r} covers no shipped version", sid)
        for old in entry.supersedes:
            if old not in by_id:
                add("unknown_reference", f"supersedes unknown source {old}", sid)
            elif effective_date(by_id[old]) >= effective_date(entry):
                add("supersedes_newer", f"supersedes {old}, which is not older", sid)
        if not entry.synthetic:
            add("not_synthetic", "all generated content must be marked synthetic: Y (Section 4.1)", sid, "warning")
    _check_supersedes_cycles(kb, add)

    # --- files on disk vs register ---------------------------------------
    for doc_type, directory in DOC_DIRS.items():
        target = data_dir / directory.relative_to(DATA_DIR)
        pattern = "TKT-*.json" if doc_type is DocType.TICKET else "*.md"
        for path in sorted(target.glob(pattern)) if target.exists() else []:
            if path.stem not in by_id or by_id[path.stem].doc_type is not doc_type:
                add("orphan_document", f"{path.relative_to(data_dir).as_posix()} has no matching register entry", path.stem)

    # --- content -----------------------------------------------------------
    digests: dict[str, str] = {}
    for doc in kb.documents.values():
        body = "\n".join(s.text for s in doc.sections).strip()
        if not body:
            add("empty_content", "document has no content", doc.source_id)
            continue
        for section in doc.sections:
            if not section.text.strip():
                add("empty_section", f"section '{section.heading}' is empty", doc.source_id)
        digest = hashlib.sha256(re.sub(r"\s+", " ", body.lower()).encode()).hexdigest()
        if digest in digests:
            add("duplicate_content", f"same content as {digests[digest]}", doc.source_id)
        digests.setdefault(digest, doc.source_id)
        if doc.ticket is not None:
            released = RELEASE_DATES.get(".".join(doc.ticket.product_version.split(".")[:2]))
            if released and doc.ticket.resolved_at < date.fromisoformat(released):
                add("version_not_released", f"ticket is on {doc.ticket.product_version}, released {released}, after it was resolved", doc.source_id)
            if not parse_version_spec(doc.product_versions).covers(doc.ticket.product_version):
                add("ticket_version_outside_scope", "ticket product_version not covered by its register product_versions", doc.source_id)
            if doc.ticket.resolved_at != doc.last_updated:
                add("ticket_date_mismatch", "last_updated must be the ticket's resolved date (Annex B)", doc.source_id)
        for gap in COVERAGE_GAPS:
            if gap.lower() in doc.content.lower():
                add("coverage_gap_mentioned", f"mentions deliberately uncovered topic {gap!r}", doc.source_id)
        flagged = scan_for_instructions(doc.content)
        labelled = "prompt_injection" in labels.get(doc.source_id, {}).get("labels", [])
        if flagged and not labelled:
            add("injection_unlabelled", f"instruction-like text ({', '.join(flagged)}) in a document not labelled prompt_injection", doc.source_id)
        if labelled and not flagged:
            add("injection_undetected", "labelled prompt_injection but the detector does not flag it", doc.source_id)

    # --- labels -------------------------------------------------------------
    for sid, row in labels.items():
        if sid not in by_id:
            add("unknown_reference", "kb_labels.csv row for unknown source", sid)
        for target in row["conflicts_with"]:
            if target not in by_id:
                add("unknown_reference", f"conflicts_with unknown source {target}", sid)
            elif by_id[target].authority_level >= by_id.get(sid, by_id[target]).authority_level and sid in by_id:
                add("conflict_authority", f"conflicts_with {target}, which does not have higher authority", sid, "warning")
    for sid in ids:
        if sid not in labels:
            add("label_missing", "no kb_labels.csv row", sid, "warning")

    # --- policy registry citations -----------------------------------------
    _check_policy_registry(kb, data_dir, add)

    # --- Section 4.1 minimums -----------------------------------------------
    counts = _counts(kb, labels, reference_date)
    if counts["article"] < MINIMUMS["article"]:
        add("minimum_articles", f"{counts['article']} help-center articles; Section 4.1 requires at least 30")
    if counts["ticket"] < MINIMUMS["ticket"]:
        add("minimum_tickets", f"{counts['ticket']} resolved tickets; Section 4.1 requires at least 25")
    if counts["angry_complaints"] < MINIMUMS["angry_complaint"]:
        add("minimum_angry", f"{counts['angry_complaints']} angry complaints; at least 3 required")
    if counts["outdated_tickets"] < MINIMUMS["outdated"]:
        add("minimum_outdated", f"{counts['outdated_tickets']} outdated/contradicted tickets; at least 3 required")
    if len(counts["major_versions"]) < 2:
        add("minimum_versions", "fewer than 2 product major versions covered")
    if not counts["future_deprecations"]:
        add("minimum_future_deprecation", "no release note announcing a deprecation on a future date")
    missing_policies = [p for p in POLICY_IDS if p not in by_id or by_id[p].doc_type is not DocType.POLICY]
    if missing_policies:
        add("minimum_policies", f"missing policy articles: {', '.join(missing_policies)}")
    return KnowledgeReport(issues=issues, counts=counts)


def _check_supersedes_cycles(kb: KnowledgeBase, add) -> None:
    graph = {e.source_id: list(e.supersedes) for e in kb.entries}

    def visit(node: str, stack: tuple[str, ...]) -> None:
        for nxt in graph.get(node, []):
            if nxt in stack:
                add("supersedes_cycle", f"supersedes cycle: {' -> '.join(stack + (nxt,))}", node)
                return
            visit(nxt, stack + (nxt,))

    for node in graph:
        visit(node, (node,))


def _check_policy_registry(kb: KnowledgeBase, data_dir: Path, add) -> None:
    from app.database.csv_io import parse_rows, read_csv

    reference = data_dir / "reference"
    raw, _ = read_csv(reference / "policy_registry.csv", "policy_registry")
    rules = [row for _, row in parse_rows("policy_registry", raw)[0]]
    for rule in rules:
        doc = kb.documents.get(rule.source_id)
        if doc is None:
            add("policy_source_missing", f"{rule.rule_id} cites {rule.source_id}, which is not in the knowledge base", rule.rule_id)
            continue
        if doc.doc_type is not DocType.POLICY:
            add("policy_source_missing", f"{rule.rule_id} cites {rule.source_id}, which is not a policy article", rule.rule_id)
        sections = {s.heading: s.text for s in doc.sections}
        if rule.source_section and rule.source_section not in sections:
            add("policy_section_missing", f"{rule.rule_id} cites section '{rule.source_section}' of {rule.source_id}, which does not exist", rule.rule_id)
            continue
        try:
            float(rule.value)
        except ValueError:
            continue
        if rule.source_section and rule.value not in _numbers(sections[rule.source_section]):
            add("policy_value_mismatch", f"{rule.rule_id} value {rule.value} does not appear in {rule.source_id} '{rule.source_section}'", rule.rule_id)

    raw_limits, _ = read_csv(reference / "plan_limits.csv", "plan_limits")
    limits = {row.plan: row for _, row in parse_rows("plan_limits", raw_limits)[0]}
    policy = kb.documents.get("KB-POL-002")
    if policy is None:
        return
    table = _plan_table("\n".join(s.text for s in policy.sections if s.heading == "Plan limits"))
    for plan, row in limits.items():
        expected = [str(row.api_rate_limit_per_min), str(row.monthly_workflow_runs), str(row.seats), row.support_tier]
        got = table.get(plan)
        if got is None or got[:4] != expected or float(got[4]) != row.monthly_price:
            add("plan_limits_mismatch", f"KB-POL-002 'Plan limits' row for {plan} does not match plan_limits.csv", "KB-POL-002")


def _counts(kb: KnowledgeBase, labels: dict[str, dict[str, Any]], reference_date: date) -> dict[str, Any]:
    by_type = Counter(e.doc_type.value for e in kb.entries)
    label_of = lambda sid: labels.get(sid, {}).get("labels", [])  # noqa: E731
    majors = sorted({v.split(".")[0] + ".x" for e in kb.entries for v in parse_version_spec(e.product_versions).covered_known_versions()})
    covered = sorted({v for e in kb.entries for v in parse_version_spec(e.product_versions).covered_known_versions()},
                     key=lambda v: tuple(int(p) for p in v.split(".")))
    future_deprecations = sorted(e.source_id for e in kb.entries if e.deprecated_on and e.deprecated_on > reference_date)
    announced = [e.source_id for e in kb.entries if e.doc_type is DocType.RELEASE_NOTE and "future_deprecation" in label_of(e.source_id)]
    return {
        "total": len(kb.entries),
        "article": by_type.get("article", 0),
        "policy": by_type.get("policy", 0),
        "release_note": by_type.get("release_note", 0),
        "ticket": by_type.get("ticket", 0),
        "community": by_type.get("community", 0),
        "angry_complaints": sum("angry_complaint" in label_of(e.source_id) for e in kb.entries),
        "outdated_tickets": sum(bool({"outdated_workaround", "conflicts_with_policy"} & set(label_of(e.source_id)))
                                for e in kb.entries if e.doc_type is DocType.TICKET),
        "deprecated": sorted(e.source_id for e in kb.entries if e.deprecated_on and e.deprecated_on <= reference_date),
        "deprecation_upcoming": future_deprecations,
        "future_deprecations": announced if future_deprecations else [],
        "superseded": sorted({old for e in kb.entries for old in e.supersedes}),
        "conflicting": sorted(sid for sid, row in labels.items() if row["conflicts_with"]),
        "prompt_injection": sorted(sid for sid in labels if "prompt_injection" in label_of(sid)),
        "version_specific": sorted(sid for sid in labels if "version_specific" in label_of(sid)),
        "major_versions": majors,
        "versions_covered": covered,
        "known_versions": list(KNOWN_VERSIONS),
    }


def render_report_markdown(report: KnowledgeReport, *, reference_date: date) -> str:
    c = report.counts
    lines = [
        "# Knowledge-base validation report",
        "",
        f"**Result:** {'PASS' if report.ok else 'FAIL'} ({len(report.errors)} errors, {len(report.warnings)} warnings). "
        f"Reference date {reference_date.isoformat()}.",
        "",
        "## Counts",
        "",
        "| Item | Count |",
        "|---|---|",
        f"| Source-register entries | {c['total']} |",
        f"| Help-center articles | {c['article']} |",
        f"| Policy articles | {c['policy']} |",
        f"| Release notes | {c['release_note']} |",
        f"| Resolved tickets | {c['ticket']} |",
        f"| Community posts | {c['community']} |",
        f"| Angry complaints (required a human) | {c['angry_complaints']} |",
        f"| Outdated / policy-contradicting tickets | {c['outdated_tickets']} |",
        f"| Deprecated (in effect) | {len(c['deprecated'])}: {', '.join(c['deprecated'])} |",
        f"| Deprecation upcoming | {len(c['deprecation_upcoming'])}: {', '.join(c['deprecation_upcoming'])} |",
        f"| Superseded | {len(c['superseded'])}: {', '.join(c['superseded'])} |",
        f"| Sources with recorded conflicts | {len(c['conflicting'])} |",
        f"| Prompt-injection fixtures | {len(c['prompt_injection'])}: {', '.join(c['prompt_injection'])} |",
        f"| Version-specific sources | {len(c['version_specific'])} |",
        f"| Product versions covered | {', '.join(c['versions_covered'])} |",
        "",
        "## Issues",
        "",
    ]
    if report.issues:
        lines += ["| Severity | Code | Source | Message |", "|---|---|---|---|"]
        lines += [f"| {i.severity} | {i.code} | {i.source_id or ''} | {i.message} |" for i in report.issues]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"
