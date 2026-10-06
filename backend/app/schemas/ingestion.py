"""Source Register metadata (Annex B) and ingestion API models.

``SourceRegisterEntry`` is the **only** metadata standard for knowledge
sources. It is one row of ``source_register.csv``, the metadata JSON of
``POST /ingest`` (Section 6: "metadata JSON with the Source Register fields")
and an item of ``GET /sources``. Field names are exactly Annex B.

Authority levels follow Annex A.1:

    1 current help-center and policy articles
    2 release notes and deprecation notices
    3 live tool results (never a document)
    4 resolved tickets
    5 customer-provided text and community posts (untrusted)
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.knowledge.versions import parse_version_spec


class DocType(str, Enum):
    """Annex B doc_type values."""

    ARTICLE = "article"
    POLICY = "policy"
    RELEASE_NOTE = "release_note"
    TICKET = "ticket"
    COMMUNITY = "community"


# Annex A.1: the authority level each document type must carry.
AUTHORITY_BY_DOC_TYPE: dict[DocType, int] = {
    DocType.ARTICLE: 1,
    DocType.POLICY: 1,
    DocType.RELEASE_NOTE: 2,
    DocType.TICKET: 4,
    DocType.COMMUNITY: 5,
}
TOOL_RESULT_AUTHORITY = 3  # live tool results; never a stored document

SOURCE_REGISTER_COLUMNS: tuple[str, ...] = (
    "source_id",
    "doc_type",
    "title",
    "authority_level",
    "product_versions",
    "last_updated",
    "effective_from",
    "deprecated_on",
    "supersedes",
    "provenance",
    "synthetic",
)

_SOURCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class SourceRegisterEntry(BaseModel):
    """One Annex B row. Lists (``supersedes``) are ``;``-separated in CSV."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: str = Field(description="e.g. KB-API-014 or TKT-2025-0311")
    doc_type: DocType
    title: str = Field(min_length=1, max_length=300)
    authority_level: int = Field(ge=1, le=5)
    product_versions: str = Field(description="Versions covered, e.g. 4.2+, 3.x, 4.0-4.1, or a comma list")
    last_updated: date = Field(description="YYYY-MM-DD (resolved date for tickets)")
    effective_from: date | None = None
    deprecated_on: date | None = None
    supersedes: list[str] = Field(default_factory=list)
    provenance: str = Field(min_length=1, max_length=300)
    synthetic: bool

    @field_validator("effective_from", "deprecated_on", mode="before")
    @classmethod
    def _optional_dates(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("source_id")
    @classmethod
    def _source_id_format(cls, value: str) -> str:
        if not _SOURCE_ID_RE.fullmatch(value):
            raise ValueError("must be upper-case segments joined by '-', e.g. KB-API-014 or TKT-2025-0311")
        return value

    @field_validator("product_versions")
    @classmethod
    def _versions_parse(cls, value: str) -> str:
        parse_version_spec(value)  # raises ValueError with a readable message
        return value

    @field_validator("supersedes", mode="before")
    @classmethod
    def _split_supersedes(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(";") if part.strip()]
        return value

    @field_validator("synthetic", mode="before")
    @classmethod
    def _yes_no(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in {"Y", "YES", "TRUE"}:
                return True
            if normalized in {"N", "NO", "FALSE"}:
                return False
            raise ValueError("must be Y or N")
        return value

    @model_validator(mode="after")
    def _dates_and_authority(self) -> "SourceRegisterEntry":
        if self.effective_from and self.deprecated_on and self.deprecated_on <= self.effective_from:
            raise ValueError("deprecated_on must be after effective_from")
        if self.source_id in self.supersedes:
            raise ValueError("a source cannot supersede itself")
        return self

    def to_csv_row(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "doc_type": self.doc_type.value,
            "title": self.title,
            "authority_level": str(self.authority_level),
            "product_versions": self.product_versions,
            "last_updated": self.last_updated.isoformat(),
            "effective_from": self.effective_from.isoformat() if self.effective_from else "",
            "deprecated_on": self.deprecated_on.isoformat() if self.deprecated_on else "",
            "supersedes": ";".join(self.supersedes),
            "provenance": self.provenance,
            "synthetic": "Y" if self.synthetic else "N",
        }


# --- ingestion API (route implemented in Phase 4) ----------------------------
class IngestRequest(BaseModel):
    """PROVISIONAL (Phase 1). Section 6 specifies multipart: a Markdown article or
    JSON ticket plus metadata JSON (``SourceRegisterEntry``). Phase 4 reshapes the
    route accordingly."""

    rebuild: bool = Field(default=False, description="Drop and rebuild the vector collection.")
    paths: list[str] | None = Field(default=None, description="Relative paths under data/knowledge_base/.")


class IngestError(BaseModel):
    source: str
    reason: str


class IngestResponse(BaseModel):
    trace_id: str
    documents_processed: int = Field(ge=0)
    chunks_indexed: int = Field(ge=0)
    documents_skipped: int = Field(default=0, ge=0)
    errors: list[IngestError] = Field(default_factory=list)


class SourceList(BaseModel):
    """``GET /sources``: the Source Register (Section 6)."""

    items: list[SourceRegisterEntry]
    total: int
