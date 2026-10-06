"""Knowledge-base content specifications (spec v1).

The CloudFlow knowledge base is defined here as structured specs: metadata,
sections and labels. The generator renders them into Markdown/JSON files and
the Source Register.

* ``seeded`` renders the specs deterministically. The seed selects among each
  ticket's customer-phrasing variants.
* ``llm`` asks Ollama to rewrite the prose of each section while keeping every
  fact (error codes, versions, numbers, UI paths). Output that drops or adds
  facts is rejected.

Provenance: the specs were authored with an AI coding assistant (disclosed in
the README, per Section 10) and are reviewable as code.

Labels (ground truth for validation and evaluation, kept out of the Annex B
register):

    version_specific       guidance differs by product version
    deprecated             deprecated_on <= reference date
    deprecation_upcoming   deprecated_on > reference date
    superseded             another source lists it in ``supersedes``
    future_deprecation     release note announcing a future deprecation
    error_code_table       contains the CF-xxx error table
    long                   long-form article
    outdated_workaround    ticket workaround contradicted by current documentation
    conflicts_with_policy  ticket resolution contradicts a policy article
    angry_complaint        angry customer, required a human
    useful_history         ticket consistent with documentation
    prompt_injection       contains text addressed to the assistant (adversarial fixture)
"""

from __future__ import annotations

from dataclasses import dataclass

SPEC_VERSION = "v1"
REFERENCE_DATE = "2026-10-06"

# Topics deliberately NOT covered, so "not covered" answers (Section 2.1) can be
# evaluated. The validator fails if any document mentions them.
COVERAGE_GAPS: tuple[str, ...] = ("SAP Ariba", "Oracle NetSuite", "on-premises installation")


@dataclass(frozen=True)
class DocSpec:
    source_id: str
    doc_type: str  # article | policy | release_note | community
    title: str
    category: str  # getting_started | account_billing | api_integrations | troubleshooting | advanced | policy | release | community
    product_versions: str
    last_updated: str
    sections: tuple[tuple[str, str], ...]
    effective_from: str | None = None
    deprecated_on: str | None = None
    supersedes: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()
    llm_rewrite: bool = True  # adversarial fixtures stay verbatim
    note: str = ""


@dataclass(frozen=True)
class TicketSpec:
    id: str
    subject: str
    question_variants: tuple[str, ...]
    intent: str  # how_to | bug | billing | account | complaint (Annex F)
    resolution: str
    tags: tuple[str, ...]
    resolved_at: str
    product_version: str
    product_versions: str  # register applicability
    escalated_to_human: bool = False
    deprecated_on: str | None = None
    labels: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()
    llm_rewrite: bool = True
    note: str = ""


def all_doc_specs() -> list[DocSpec]:
    from app.knowledge.catalog import articles, other, policies

    return [*policies.POLICIES, *articles.ARTICLES, *other.RELEASE_NOTES, *other.COMMUNITY]


def all_ticket_specs() -> list[TicketSpec]:
    from app.knowledge.catalog import tickets

    return list(tickets.TICKETS)
