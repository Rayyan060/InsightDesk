"""Normalised knowledge documents and the knowledge-base loader.

Storage layout (single source of truth for metadata: the Source Register):

    data/source_register/source_register.csv     Annex B, one row per source
    data/knowledge_base/articles/<id>.md          doc_type article
    data/knowledge_base/policies/<id>.md          doc_type policy
    data/knowledge_base/release_notes/<id>.md     doc_type release_note
    data/knowledge_base/community/<id>.md         doc_type community
    data/tickets/<id>.json                        doc_type ticket (Annex F fields)

Markdown files hold content only: ``# Title`` then ``## Section`` blocks. No
front matter, so metadata never disagrees with the register. A
``KnowledgeDocument`` is the register entry plus the parsed content. That is
the retrieval-ready representation Phase 4 chunks by section, and every
section carries the citation fields R3 requires (source ID, section, product
versions, last-updated date).
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import PROJECT_ROOT
from app.knowledge.versions import parse_version
from app.schemas.ingestion import SOURCE_REGISTER_COLUMNS, DocType, SourceRegisterEntry

DATA_DIR = PROJECT_ROOT / "data"
KB_DIR = DATA_DIR / "knowledge_base"
TICKETS_DIR = DATA_DIR / "tickets"
REGISTER_DIR = DATA_DIR / "source_register"
REGISTER_PATH = REGISTER_DIR / "source_register.csv"
LABELS_PATH = REGISTER_DIR / "kb_labels.csv"

DOC_DIRS: dict[DocType, Path] = {
    DocType.ARTICLE: KB_DIR / "articles",
    DocType.POLICY: KB_DIR / "policies",
    DocType.RELEASE_NOTE: KB_DIR / "release_notes",
    DocType.COMMUNITY: KB_DIR / "community",
    DocType.TICKET: TICKETS_DIR,
}

TICKET_ID_RE = re.compile(r"^TKT-\d{4}-\d{4}$")
TicketIntent = Literal["how_to", "bug", "billing", "account", "complaint"]


class TicketRecord(BaseModel):
    """Resolved ticket JSON. Annex F fields plus subject/product_version/escalation flag."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    subject: str = Field(min_length=1)
    customer_question: str = Field(min_length=1)
    intent: TicketIntent
    resolution: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    resolved_at: date
    product_version: str
    escalated_to_human: bool = False

    @field_validator("id")
    @classmethod
    def _id_format(cls, value: str) -> str:
        if not TICKET_ID_RE.fullmatch(value):
            raise ValueError("ticket id must look like TKT-2025-0311")
        return value

    @field_validator("product_version")
    @classmethod
    def _version(cls, value: str) -> str:
        parse_version(value)
        return value


class Section(BaseModel):
    heading: str
    text: str


class KnowledgeDocument(SourceRegisterEntry):
    """Annex B metadata + content. The normalised, retrieval-ready document."""

    content: str
    sections: list[Section]
    path: str
    ticket: TicketRecord | None = None


# ---------------------------------------------------------------------- #
# Markdown
# ---------------------------------------------------------------------- #
def parse_markdown(text: str) -> tuple[str | None, list[Section]]:
    """Return the ``# Title`` and the ``## Section`` blocks (text before the first H2 becomes 'Introduction')."""
    title: str | None = None
    sections: list[Section] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if heading is not None or body:
            sections.append(Section(heading=heading or "Introduction", text=body))

    for line in text.splitlines():
        if line.startswith("# ") and title is None and heading is None and not buffer:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            flush()
            heading, buffer = line[3:].strip(), []
            continue
        buffer.append(line)
    flush()
    return title, sections


def render_markdown(title: str, sections: list[tuple[str, str]]) -> str:
    parts = [f"# {title}", ""]
    for heading, body in sections:
        parts += [f"## {heading}", "", body.strip(), ""]
    return "\n".join(parts).rstrip() + "\n"


def ticket_markdown(ticket: TicketRecord) -> str:
    return render_markdown(
        ticket.subject,
        [
            ("Customer question", ticket.customer_question),
            ("Resolution", ticket.resolution),
            ("Details", f"Product version: {ticket.product_version}. Resolved: {ticket.resolved_at.isoformat()}. "
                        f"Escalated to a human: {'yes' if ticket.escalated_to_human else 'no'}. Tags: {', '.join(ticket.tags)}."),
        ],
    )


def document_path(doc_type: DocType, source_id: str) -> Path:
    suffix = ".json" if doc_type is DocType.TICKET else ".md"
    return DOC_DIRS[doc_type] / f"{source_id}{suffix}"


# ---------------------------------------------------------------------- #
# Register IO
# ---------------------------------------------------------------------- #
@dataclass
class LoadIssue:
    code: str
    message: str
    source_id: str | None = None
    severity: Literal["error", "warning"] = "error"


def read_register(path: Path = REGISTER_PATH) -> tuple[list[SourceRegisterEntry], list[LoadIssue], list[dict[str, str]]]:
    """Parse the register; returns (valid entries, issues, raw rows)."""
    issues: list[LoadIssue] = []
    if not path.exists():
        return [], [LoadIssue("register_missing", f"{path.name} not found")], []
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [h.strip() for h in (reader.fieldnames or [])]
    if tuple(header) != SOURCE_REGISTER_COLUMNS:
        issues.append(LoadIssue("register_columns", f"columns must be exactly Annex B: {', '.join(SOURCE_REGISTER_COLUMNS)}"))
        return [], issues, []
    entries, raw_rows = [], []
    for line, row in enumerate(reader, start=2):
        raw_rows.append(row)
        missing = [c for c in ("source_id", "doc_type", "title", "authority_level", "product_versions", "last_updated", "provenance", "synthetic")
                   if not (row.get(c) or "").strip()]
        if missing:
            issues.append(LoadIssue("missing_metadata", f"line {line}: missing {', '.join(missing)}", row.get("source_id") or None))
            continue
        try:
            entries.append(SourceRegisterEntry.model_validate(row))
        except ValidationError as exc:
            for err in exc.errors(include_input=False, include_url=False):
                column = ".".join(str(p) for p in err["loc"]) or "row"
                issues.append(LoadIssue("invalid_metadata", f"line {line} {column}: {err['msg']}", row.get("source_id")))
    return entries, issues, raw_rows


def write_register(entries: list[SourceRegisterEntry], path: Path = REGISTER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SOURCE_REGISTER_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for entry in sorted(entries, key=lambda e: e.source_id):
            writer.writerow(entry.to_csv_row())


# ---------------------------------------------------------------------- #
# Loading
# ---------------------------------------------------------------------- #
@dataclass
class KnowledgeBase:
    documents: dict[str, KnowledgeDocument] = field(default_factory=dict)
    entries: list[SourceRegisterEntry] = field(default_factory=list)
    issues: list[LoadIssue] = field(default_factory=list)
    raw_rows: list[dict[str, str]] = field(default_factory=list)

    def by_type(self, doc_type: DocType) -> list[KnowledgeDocument]:
        return sorted((d for d in self.documents.values() if d.doc_type is doc_type), key=lambda d: d.source_id)


def load_document(entry: SourceRegisterEntry, data_dir: Path = DATA_DIR) -> tuple[KnowledgeDocument | None, list[LoadIssue]]:
    path = data_dir / document_path(entry.doc_type, entry.source_id).relative_to(DATA_DIR)
    if not path.exists():
        return None, [LoadIssue("document_missing", f"no document file for register entry ({path.name})", entry.source_id)]
    issues: list[LoadIssue] = []
    ticket = None
    raw = path.read_text(encoding="utf-8")
    if entry.doc_type is DocType.TICKET:
        try:
            ticket = TicketRecord.model_validate(json.loads(raw))
        except (ValueError, ValidationError) as exc:
            return None, [LoadIssue("invalid_ticket", f"{path.name}: {str(exc).splitlines()[0]}", entry.source_id)]
        if ticket.id != entry.source_id:
            issues.append(LoadIssue("ticket_id_mismatch", "ticket id differs from register source_id", entry.source_id))
        content = ticket_markdown(ticket)
    else:
        content = raw
    title, sections = parse_markdown(content)
    if title is None:
        issues.append(LoadIssue("missing_title", "document has no '# Title' line", entry.source_id))
    elif title != entry.title:
        issues.append(LoadIssue("title_mismatch", "document title differs from the register title", entry.source_id))
    document = KnowledgeDocument(
        **entry.model_dump(), content=content, sections=sections, path=str(path.relative_to(data_dir.parent)).replace("\\", "/"), ticket=ticket
    )
    return document, issues


def load_knowledge_base(data_dir: Path = DATA_DIR) -> KnowledgeBase:
    register_path = data_dir / "source_register" / "source_register.csv"
    entries, issues, raw_rows = read_register(register_path)
    kb = KnowledgeBase(entries=entries, issues=issues, raw_rows=raw_rows)
    for entry in entries:
        if entry.source_id in kb.documents:
            continue  # duplicate IDs are reported by the validator
        document, doc_issues = load_document(entry, data_dir)
        kb.issues.extend(doc_issues)
        if document is not None:
            kb.documents[entry.source_id] = document
    return kb


def section_records(document: KnowledgeDocument, superseded_by: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Retrieval-ready units (one per section) carrying every citation and precedence field."""
    records = []
    for index, section in enumerate(document.sections):
        records.append(
            {
                "chunk_id": f"{document.source_id}#{index}",
                "source_id": document.source_id,
                "doc_type": document.doc_type.value,
                "title": document.title,
                "section": section.heading,
                "text": section.text,
                "authority_level": document.authority_level,
                "product_versions": document.product_versions,
                "last_updated": document.last_updated.isoformat(),
                "effective_from": document.effective_from.isoformat() if document.effective_from else None,
                "deprecated_on": document.deprecated_on.isoformat() if document.deprecated_on else None,
                "supersedes": document.supersedes,
                "superseded_by": (superseded_by or {}).get(document.source_id, []),
                "synthetic": document.synthetic,
            }
        )
    return records
