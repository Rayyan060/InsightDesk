"""Phase 3: the committed knowledge base, Source Register, policy articles and guide minimums."""

from __future__ import annotations

import csv
import json
from datetime import date

import pytest

from app.database.csv_io import parse_rows, read_csv
from app.knowledge.catalog import COVERAGE_GAPS
from app.knowledge.documents import DATA_DIR, LABELS_PATH, REGISTER_PATH, load_knowledge_base
from app.knowledge.validation import read_labels, validate_knowledge
from app.knowledge.versions import parse_version_spec
from app.schemas.ingestion import AUTHORITY_BY_DOC_TYPE, SOURCE_REGISTER_COLUMNS, DocType

REF = date(2026, 10, 6)


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def report(kb):
    return validate_knowledge(DATA_DIR, reference_date=REF, kb=kb)


@pytest.fixture(scope="module")
def policy_rules():
    raw, _ = read_csv(DATA_DIR / "reference" / "policy_registry.csv", "policy_registry")
    return [row for _, row in parse_rows("policy_registry", raw)[0]]


def test_committed_knowledge_base_validates_clean(report) -> None:
    assert report.errors == [], [i.to_dict() for i in report.errors]
    assert report.warnings == [], [i.to_dict() for i in report.warnings]


def test_section_4_1_minimums(report) -> None:
    c = report.counts
    assert c["article"] >= 30 and c["ticket"] >= 25
    assert c["angry_complaints"] >= 3 and c["outdated_tickets"] >= 3
    assert c["major_versions"] == ["3.x", "4.x"]
    assert c["future_deprecations"] == ["RN-2026-09"]
    assert all(c[doc_type] > 0 for doc_type in ("article", "policy", "release_note", "ticket", "community"))


def test_register_is_exactly_annex_b(kb) -> None:
    with REGISTER_PATH.open(encoding="utf-8", newline="") as handle:
        assert tuple(csv.DictReader(handle).fieldnames) == SOURCE_REGISTER_COLUMNS
    ids = [e.source_id for e in kb.entries]
    assert len(ids) == len(set(ids)) == len(kb.documents)
    for entry in kb.entries:
        assert entry.authority_level == AUTHORITY_BY_DOC_TYPE[entry.doc_type], entry.source_id
        assert entry.synthetic is True
        assert entry.provenance
        assert parse_version_spec(entry.product_versions).covered_known_versions(), entry.source_id
        assert not entry.source_id.startswith("JD-")


def test_six_policy_articles_with_registry_sections(kb, policy_rules) -> None:
    policies = {d.source_id: d for d in kb.by_type(DocType.POLICY)}
    assert sorted(policies) == [f"KB-POL-00{n}" for n in range(1, 7)]
    for rule in policy_rules:
        doc = policies[rule.source_id]
        headings = {s.heading: s.text for s in doc.sections}
        assert rule.source_section in headings, (rule.rule_id, rule.source_section)
        try:
            float(rule.value)
        except ValueError:
            continue
        assert rule.value in headings[rule.source_section].replace(",", ""), rule.rule_id


def test_policy_articles_are_substantive(kb) -> None:
    for doc in kb.by_type(DocType.POLICY):
        words = len(doc.content.split())
        assert words >= 80, (doc.source_id, words)


def test_plan_limits_policy_matches_reference_table(kb) -> None:
    text = next(s.text for s in kb.documents["KB-POL-002"].sections if s.heading == "Plan limits")
    raw, _ = read_csv(DATA_DIR / "reference" / "plan_limits.csv", "plan_limits")
    for _, plan in parse_rows("plan_limits", raw)[0]:
        row = next(line for line in text.splitlines() if line.startswith(f"| {plan.plan} |"))
        cells = [c.strip().replace(",", "") for c in row.strip("|").split("|")]
        assert cells[1:5] == [str(plan.api_rate_limit_per_min), str(plan.monthly_workflow_runs), str(plan.seats), plan.support_tier]


def test_guide_example_sources_exist_as_described(kb) -> None:
    adv = kb.documents["KB-ADV-007"]
    assert (adv.doc_type, adv.product_versions, adv.last_updated.isoformat()) == (DocType.ARTICLE, "4.2+", "2026-09-10")
    assert "Steps" in [s.heading for s in adv.sections]  # Section 6.1 citation example
    tokens = kb.documents["KB-API-014"]
    assert (tokens.title, tokens.product_versions, tokens.last_updated.isoformat(), tokens.supersedes) == (
        "Rotating API tokens", "4.0+", "2026-08-20", ["KB-API-009"])  # Annex B example
    assert "Duplicate charges" in [s.heading for s in kb.documents["KB-BIL-003"].sections]  # Annex D example


def test_all_five_annex_f_categories_present() -> None:
    labels = read_labels(LABELS_PATH)
    categories = {row["category"] for row in labels.values() if row["doc_type"] == "article"}
    assert {"getting_started", "account_billing", "api_integrations", "troubleshooting", "advanced"} <= categories


def test_tickets_have_annex_f_fields(kb) -> None:
    for doc in kb.by_type(DocType.TICKET):
        raw = json.loads((DATA_DIR / "tickets" / f"{doc.source_id}.json").read_text(encoding="utf-8"))
        assert {"id", "customer_question", "intent", "resolution", "tags", "resolved_at"} <= set(raw)
        assert raw["intent"] in {"how_to", "bug", "billing", "account", "complaint"}
        assert doc.last_updated.isoformat() == raw["resolved_at"]


def test_version_variation_exists(kb) -> None:
    export_docs = {sid: kb.documents[sid].product_versions for sid in ("KB-ADV-005", "KB-ADV-006", "KB-ADV-007")}
    assert export_docs == {"KB-ADV-005": "3.x", "KB-ADV-006": "4.0-4.1", "KB-ADV-007": "4.2+"}
    covered = {v for e in kb.entries for v in parse_version_spec(e.product_versions).covered_known_versions()}
    assert covered == {"3.8", "3.9", "4.0", "4.1", "4.2", "4.3"}  # every version in the Phase 2 account data


def test_deprecated_outdated_and_conflicting_sources(report) -> None:
    c = report.counts
    assert {"KB-ADV-003", "TKT-2025-0414"} <= set(c["deprecated"])
    assert "KB-API-002" in c["deprecation_upcoming"]
    assert set(c["superseded"]) == {"KB-API-009", "KB-ADV-003"}
    assert {"TKT-2025-0342", "TKT-2025-0398", "TKT-2025-0450", "TKT-2025-0472", "TKT-2025-0366", "COM-0001"} <= set(c["conflicting"])


def test_coverage_gaps_remain_uncovered(kb) -> None:
    for doc in kb.documents.values():
        for gap in COVERAGE_GAPS:
            assert gap.lower() not in doc.content.lower(), (doc.source_id, gap)


def test_phase2_policy_citations_now_verified() -> None:
    from app.synthetic.pipeline import policy_source_ids

    assert policy_source_ids() == {f"KB-POL-00{n}" for n in range(1, 7)}
