"""Source-precedence *metadata* (Annex A), for deterministic filtering in Phase 4.

This module answers "may this source be used for this customer, on this
date?" and exposes authority information. It does **not** rank retrieval
results; ranking (Annex A.2 steps 3–5 applied to retrieved candidates) is
Phase 4.

Annex A.2, as implemented here:

1. **Applicability.** The source's ``product_versions`` cover the customer's
   version, it is in effect on ``as_of_date`` (``effective_from <= as_of``),
   and it is not deprecated (``deprecated_on > as_of`` or empty). A deprecation
   that hasn't taken effect yet is a *notice*, not an exclusion ("mention
   upcoming deprecations").
2. **Explicit supersession.** If B lists A in ``supersedes``, and B is in
   effect on ``as_of`` and applies to the customer's version, A is superseded
   from B's effective date (``effective_from``, or ``last_updated`` when B has
   none).
3. **Authority.** ``authority_level`` 1 (articles, policies) beats 2 (release
   notes), 3 (live tool results), 4 (resolved tickets) and 5 (community,
   customer text) regardless of date. Tickets add detail but never contradict
   documentation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from app.knowledge.versions import parse_version_spec
from app.schemas.ingestion import SourceRegisterEntry

AUTHORITY_LABELS: dict[int, str] = {
    1: "current help-center or policy article",
    2: "release note or deprecation notice",
    3: "live tool result",
    4: "resolved ticket (historical evidence only)",
    5: "untrusted: customer or community text",
}


def effective_date(entry: SourceRegisterEntry) -> date:
    return entry.effective_from or entry.last_updated


def superseded_by_map(entries: Iterable[SourceRegisterEntry]) -> dict[str, list[str]]:
    inverse: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        for old in entry.supersedes:
            inverse[old].append(entry.source_id)
    return {k: sorted(v) for k, v in inverse.items()}


@dataclass
class Applicability:
    source_id: str
    applicable: bool
    reasons: list[str] = field(default_factory=list)  # why excluded
    notices: list[str] = field(default_factory=list)  # e.g. upcoming deprecation


def applicability(
    entry: SourceRegisterEntry,
    *,
    as_of: date,
    product_version: str | None = None,
    entries_by_id: dict[str, SourceRegisterEntry] | None = None,
    superseded_by: dict[str, list[str]] | None = None,
) -> Applicability:
    reasons: list[str] = []
    notices: list[str] = []
    spec = parse_version_spec(entry.product_versions)
    if product_version is not None and not spec.covers(product_version):
        reasons.append("version_not_covered")
    if entry.effective_from and entry.effective_from > as_of:
        reasons.append("not_yet_effective")
    if entry.deprecated_on:
        if entry.deprecated_on <= as_of:
            reasons.append("deprecated")
        else:
            notices.append(f"deprecation_upcoming:{entry.deprecated_on.isoformat()}")
    for newer_id in (superseded_by or {}).get(entry.source_id, []):
        newer = (entries_by_id or {}).get(newer_id)
        if newer is None or effective_date(newer) > as_of:
            continue
        if product_version is not None and not parse_version_spec(newer.product_versions).covers(product_version):
            continue
        reasons.append(f"superseded_by:{newer_id}")
    return Applicability(entry.source_id, not reasons, reasons, notices)
