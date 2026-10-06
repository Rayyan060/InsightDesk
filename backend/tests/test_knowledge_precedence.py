"""Version grammar and Annex A precedence metadata (applicability, deprecation, supersession, authority)."""

from __future__ import annotations

from datetime import date

import pytest

from app.knowledge.documents import load_knowledge_base, section_records
from app.knowledge.precedence import applicability, superseded_by_map
from app.knowledge.versions import parse_version_spec


@pytest.mark.parametrize(
    ("spec", "covered", "not_covered"),
    [
        ("4.2+", ["4.2", "4.3", "4.2.1"], ["4.1", "3.9"]),
        ("3.x", ["3.8", "3.9"], ["4.0"]),
        ("4.0-4.1", ["4.0", "4.1"], ["3.9", "4.2"]),
        ("4.3", ["4.3", "4.3.2"], ["4.2"]),
        ("3.x, 4.0", ["3.8", "4.0"], ["4.1"]),
        ("all", ["3.8", "4.3"], []),
    ],
)
def test_version_grammar(spec, covered, not_covered) -> None:
    parsed = parse_version_spec(spec)
    assert all(parsed.covers(v) for v in covered)
    assert not any(parsed.covers(v) for v in not_covered)


@pytest.mark.parametrize("bad", ["", "4", "v4.2", "4.2-4.0", "latest", "4.x+"])
def test_invalid_version_specs_rejected(bad) -> None:
    with pytest.raises(ValueError):
        parse_version_spec(bad)


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def ctx(kb):
    return {"entries_by_id": {e.source_id: e for e in kb.entries}, "superseded_by": superseded_by_map(kb.entries)}


def _app(kb, ctx, sid, version, day):
    return applicability(kb.documents[sid], as_of=date.fromisoformat(day), product_version=version, **ctx)


def test_deprecated_document_excluded_only_after_its_date(kb, ctx) -> None:
    before = _app(kb, ctx, "KB-ADV-003", "3.9", "2026-06-29")
    after = _app(kb, ctx, "KB-ADV-003", "3.9", "2026-06-30")
    assert before.applicable and not after.applicable and "deprecated" in after.reasons


def test_upcoming_deprecation_is_a_notice_not_an_exclusion(kb, ctx) -> None:
    result = _app(kb, ctx, "KB-API-002", "3.9", "2026-10-06")
    assert result.applicable and result.notices == ["deprecation_upcoming:2026-12-01"]
    assert not _app(kb, ctx, "KB-API-002", "3.9", "2026-12-01").applicable


def test_supersession_from_effective_date(kb, ctx) -> None:
    assert _app(kb, ctx, "KB-API-009", "4.3", "2026-08-19").applicable
    later = _app(kb, ctx, "KB-API-009", "4.3", "2026-08-20")
    assert not later.applicable and later.reasons == ["superseded_by:KB-API-014"]


def test_supersession_respects_customer_version(kb, ctx) -> None:
    # KB-ADV-004 (Schedules, 4.1+) supersedes cron triggers only for versions it covers:
    # before cron's 2026-06-30 deprecation, 3.9 and 4.0 customers still get the cron article.
    for version in ("3.9", "4.0"):
        result = _app(kb, ctx, "KB-ADV-003", version, "2026-03-01")
        assert result.applicable and result.reasons == [], version


def test_not_yet_effective(kb, ctx) -> None:
    result = _app(kb, ctx, "KB-ADV-004", "4.3", "2026-02-01")
    assert "not_yet_effective" in result.reasons


def test_version_specific_documents_select_by_version(kb, ctx) -> None:
    applicable = {
        v: [sid for sid in ("KB-ADV-005", "KB-ADV-006", "KB-ADV-007") if _app(kb, ctx, sid, v, "2026-10-06").applicable]
        for v in ("3.8", "4.1", "4.3")
    }
    assert applicable == {"3.8": ["KB-ADV-005"], "4.1": ["KB-ADV-006"], "4.3": ["KB-ADV-007"]}


def test_outdated_ticket_is_lower_authority_than_the_documentation_it_contradicts(kb, ctx) -> None:
    ticket, doc = kb.documents["TKT-2025-0342"], kb.documents["KB-TRB-002"]
    # Both apply to a 3.9 customer, so filtering alone cannot resolve them: authority must (Annex A.2 step 3).
    assert _app(kb, ctx, "TKT-2025-0342", "3.9", "2026-10-06").applicable
    assert _app(kb, ctx, "KB-TRB-002", "3.9", "2026-10-06").applicable
    assert ticket.authority_level == 4 and doc.authority_level == 1
    assert "SSL" in ticket.content and "cannot be turned off" in doc.content


def test_deprecated_ticket_excluded(kb, ctx) -> None:
    assert not _app(kb, ctx, "TKT-2025-0414", "3.9", "2026-10-06").applicable


def test_section_records_are_citation_ready(kb, ctx) -> None:
    records = section_records(kb.documents["KB-ADV-007"], ctx["superseded_by"])
    steps = next(r for r in records if r["section"] == "Steps")
    assert {k: steps[k] for k in ("source_id", "doc_type", "product_versions", "last_updated", "authority_level")} == {
        "source_id": "KB-ADV-007", "doc_type": "article", "product_versions": "4.2+", "last_updated": "2026-09-10", "authority_level": 1,
    }
    old = section_records(kb.documents["KB-API-009"], ctx["superseded_by"])[0]
    assert old["superseded_by"] == ["KB-API-014"]
