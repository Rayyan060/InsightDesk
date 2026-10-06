"""Ingest the validated knowledge base into ChromaDB (idempotent; source files are never modified).

    python scripts/ingest_knowledge.py                    # sentence-transformers (EMBEDDING_MODEL)
    python scripts/ingest_knowledge.py --embedder hashing # no model download (lexical fallback)
"""

from __future__ import annotations

import argparse

from app.cli.common import out, setup_logging
from app.core.config import load_settings
from app.rag.embeddings import HASHING_NAME, get_embedding_provider
from app.rag.ingestion import COLLECTION, ingest
from app.rag.vector_store import open_chroma_client


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ingest_knowledge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--embedder", choices=["model", "hashing"], default="model")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    setup_logging(args.verbose)

    settings = load_settings()
    if settings.resolved_chroma_dir is None:
        out("error: CHROMA_PERSIST_DIR is not set")
        return 2
    embedder = get_embedding_provider(HASHING_NAME if args.embedder == "hashing" else settings.embedding_model)
    client = open_chroma_client(settings.resolved_chroma_dir)
    result = ingest(client, embedder)
    out(f"Ingested {result.documents} documents as {result.chunks} chunks into '{COLLECTION}' "
        f"({settings.resolved_chroma_dir}) with {result.embedder}; removed {result.deleted} stale chunks"
        + ("; collection rebuilt for a new embedder" if result.rebuilt else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
