"""Knowledge-base ingestion into ChromaDB (idempotent; never modifies source documents).

One chunk per document section (``section_records``): sections are the
citation unit (R3) and are short enough to embed whole. Every chunk carries
Annex B metadata, so retrieval can filter and rank deterministically.

Idempotency: chunk IDs are stable (``<source_id>#<n>``), so re-running upserts
the same IDs and deletes chunks whose source no longer exists. If the embedder
changes, the collection is rebuilt, because vectors from different models
can't be mixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.knowledge.documents import DATA_DIR, KnowledgeBase, load_knowledge_base, section_records
from app.knowledge.precedence import superseded_by_map
from app.knowledge.safety import scan_for_instructions
from app.rag.embeddings import EmbeddingProvider

COLLECTION = "insightdesk_kb"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str  # what is embedded
    content: str  # section body shown to users / used as evidence
    metadata: dict[str, Any]


def build_chunks(kb: KnowledgeBase) -> list[Chunk]:
    superseded = superseded_by_map(kb.entries)
    chunks = []
    for doc in sorted(kb.documents.values(), key=lambda d: d.source_id):
        flags = ";".join(scan_for_instructions(doc.content))
        for record in section_records(doc, superseded):
            metadata = {
                "source_id": record["source_id"],
                "doc_type": record["doc_type"],
                "title": record["title"],
                "section": record["section"],
                "product_versions": record["product_versions"],
                "last_updated": record["last_updated"],
                "effective_from": record["effective_from"] or "",
                "deprecated_on": record["deprecated_on"] or "",
                "authority_level": record["authority_level"],
                "supersedes": ";".join(record["supersedes"]),
                "superseded_by": ";".join(record["superseded_by"]),
                "provenance": doc.provenance,
                "injection_flags": flags,
            }
            text = f"{record['title']}. {record['section']}. {record['text']}"
            chunks.append(Chunk(record["chunk_id"], text, record["text"], metadata))
    return chunks


@dataclass
class IngestResult:
    documents: int
    chunks: int
    upserted: int
    deleted: int
    rebuilt: bool
    embedder: str


def ingest(client: Any, embedder: EmbeddingProvider, *, data_dir: Path = DATA_DIR, collection: str = COLLECTION) -> IngestResult:
    kb = load_knowledge_base(data_dir)
    errors = [i for i in kb.issues if i.severity == "error"]
    if errors:
        raise ValueError(f"knowledge base has {len(errors)} load errors; run scripts/validate_knowledge.py")
    chunks = build_chunks(kb)

    rebuilt = False
    existing_names = {c.name if hasattr(c, "name") else c for c in client.list_collections()}
    if collection in existing_names:
        current = client.get_collection(collection)
        if (current.metadata or {}).get("embedder") != embedder.model_name:
            client.delete_collection(collection)
            rebuilt = True
    coll = client.get_or_create_collection(collection, metadata={"embedder": embedder.model_name, "hnsw:space": "cosine"})

    stale = set(coll.get(include=[])["ids"]) - {c.chunk_id for c in chunks}
    if stale:
        coll.delete(ids=sorted(stale))
    for start in range(0, len(chunks), 64):
        batch = chunks[start:start + 64]
        coll.upsert(
            ids=[c.chunk_id for c in batch],
            embeddings=embedder.embed([c.text for c in batch]),
            documents=[c.content for c in batch],
            metadatas=[c.metadata for c in batch],
        )
    return IngestResult(len(kb.documents), len(chunks), len(chunks), len(stale), rebuilt, embedder.model_name)
