"""Document chunking (Phase 3).

Planned: heading-aware splitting of knowledge-base documents into chunks of
bounded size with overlap, preserving section titles and document metadata
(doc_id, version, effective_date) on every chunk for citation and precedence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import NotImplementedFeatureError


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    section: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_document(doc_id: str, text: str, metadata: dict[str, Any]) -> list[Chunk]:
    raise NotImplementedFeatureError("Document chunking", planned_phase="Phase 3")
