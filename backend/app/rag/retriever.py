"""Version-aware retrieval with Annex A precedence.

1. Vector search (ChromaDB, or an in-memory index when Chroma isn't configured)
   returns a candidate pool.
2. **Applicability filter** (Annex A.2 steps 1–2, ``app.knowledge.precedence``):
   drop candidates whose ``product_versions`` don't cover the customer's
   version, that aren't yet effective, that are deprecated, or that are
   superseded on ``as_of``.
3. **Authority-aware ranking** (A.2 steps 3–4): among candidates within
   ``RELEVANCE_RATIO`` of the best similarity, articles and policies (1)
   rank before release notes (2), resolved tickets (4) and community posts (5).
   So authoritative documentation outranks historical tickets even when a
   ticket's wording matches the query more closely. Within a tier, the order is
   score (similarity + authority bonus), then recency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.knowledge.documents import KnowledgeBase, load_knowledge_base
from app.knowledge.precedence import applicability, superseded_by_map
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.rag.ingestion import COLLECTION, Chunk, build_chunks
from app.schemas.ingestion import SourceRegisterEntry

AUTHORITY_BONUS = {1: 0.10, 2: 0.05, 3: 0.0, 4: -0.10, 5: -0.25}
# Relative, because absolute similarity scales differ by embedder (lexical vs semantic).
# Tuned heuristic: a documentation chunk at >= 65% of the best match is on-topic
# (observed: an old ticket's near-verbatim wording 0.82 vs the refund policy 0.56).
RELEVANCE_RATIO = 0.65


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_id: str
    title: str
    section: str
    content: str
    metadata: dict[str, Any]
    distance: float
    similarity: float
    score: float
    notices: list[str] = field(default_factory=list)

    @property
    def authority_level(self) -> int:
        return int(self.metadata["authority_level"])


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    excluded: dict[str, list[str]]  # source_id -> reasons (for audit)


class VectorIndex(Protocol):
    def query(self, embedding: list[float], n: int) -> list[tuple[str, str, dict[str, Any], float]]: ...


class MemoryIndex:
    """Exact cosine search over all chunks (small corpus); used without Chroma and in tests."""

    def __init__(self, chunks: list[Chunk], embedder: EmbeddingProvider) -> None:
        self.chunks = chunks
        self.vectors = embedder.embed([c.text for c in chunks])

    def query(self, embedding: list[float], n: int):
        scored = []
        for chunk, vec in zip(self.chunks, self.vectors):
            cosine = sum(a * b for a, b in zip(embedding, vec))
            scored.append((chunk.chunk_id, chunk.content, chunk.metadata, 1.0 - cosine))
        return sorted(scored, key=lambda item: item[3])[:n]


class ChromaIndex:
    def __init__(self, collection: Any) -> None:
        self.collection = collection

    def query(self, embedding: list[float], n: int):
        result = self.collection.query(query_embeddings=[embedding], n_results=n, include=["documents", "metadatas", "distances"])
        return list(zip(result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]))


class Retriever:
    def __init__(self, index: VectorIndex, embedder: EmbeddingProvider, entries: list[SourceRegisterEntry], *, backend: str) -> None:
        self.index = index
        self.embedder = embedder
        self.entries = {e.source_id: e for e in entries}
        self.superseded_by = superseded_by_map(entries)
        self.backend = backend

    def retrieve(self, query: str, *, product_version: str | None = None, as_of: date | None = None,
                 k: int = 5, candidates: int = 40) -> RetrievalResult:
        as_of = as_of or date.today()
        hits = self.index.query(self.embedder.embed([query])[0], candidates)
        kept: list[RetrievedChunk] = []
        excluded: dict[str, list[str]] = {}
        for chunk_id, content, metadata, distance in hits:
            entry = self.entries.get(metadata["source_id"])
            if entry is None:  # index out of date with the register
                excluded[metadata["source_id"]] = ["not_in_register"]
                continue
            verdict = applicability(entry, as_of=as_of, product_version=product_version,
                                    entries_by_id=self.entries, superseded_by=self.superseded_by)
            if not verdict.applicable:
                excluded[entry.source_id] = verdict.reasons
                continue
            similarity = 1.0 - float(distance)
            score = similarity + AUTHORITY_BONUS.get(int(metadata["authority_level"]), 0.0)
            kept.append(RetrievedChunk(chunk_id, entry.source_id, metadata["title"], metadata["section"], content,
                                       dict(metadata), float(distance), round(similarity, 4), round(score, 4), verdict.notices))
        # Annex A.2 step 3 (authority prevails): among candidates in the relevance band
        # (similarity >= RELEVANCE_RATIO x the best match), higher authority ranks
        # first, so a near-verbatim old ticket cannot outrank the documentation.
        # Less relevant candidates follow. Ties go to higher score, then the most recent source.
        best = max((c.similarity for c in kept), default=0.0)
        kept.sort(key=lambda c: c.metadata["last_updated"], reverse=True)
        kept.sort(key=lambda c: (c.similarity < best * RELEVANCE_RATIO, c.authority_level, -c.score))
        return RetrievalResult(kept[:k], excluded)


def memory_retriever(kb: KnowledgeBase | None = None, embedder: EmbeddingProvider | None = None) -> Retriever:
    kb = kb or load_knowledge_base()
    embedder = embedder or get_embedding_provider("hashing-bow-512")
    return Retriever(MemoryIndex(build_chunks(kb), embedder), embedder, kb.entries, backend=f"memory/{embedder.model_name}")


def chroma_retriever(client: Any, entries: list[SourceRegisterEntry], collection: str = COLLECTION) -> Retriever | None:
    """Retriever over an ingested collection, or None if it hasn't been ingested yet."""
    names = {c.name if hasattr(c, "name") else c for c in client.list_collections()}
    if collection not in names:
        return None
    coll = client.get_collection(collection)
    if coll.count() == 0:
        return None
    embedder = get_embedding_provider((coll.metadata or {}).get("embedder", "all-MiniLM-L6-v2"))
    return Retriever(ChromaIndex(coll), embedder, entries, backend=f"chroma/{embedder.model_name}")
