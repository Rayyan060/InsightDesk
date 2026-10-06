"""ChromaDB client lifecycle.

Added beyond the prescribed layout so the client is created once in the
application lifespan and shared by health checks (Phase 1) and the retriever
and ingestion pipeline (Phase 3), instead of each module opening its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChromaStatus:
    reachable: bool
    collection_count: int | None = None
    error: str | None = None


def open_chroma_client(persist_dir: Path) -> Any:
    """Open a persistent Chroma client with telemetry disabled.

    Raises ImportError if chromadb is not installed, or the underlying error if
    the directory cannot be opened. Callers decide how to degrade.
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(persist_dir),
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False),
    )


def check_chroma(client: Any) -> ChromaStatus:
    """Heartbeat plus collection count. Never raises."""
    try:
        client.heartbeat()
        return ChromaStatus(reachable=True, collection_count=len(client.list_collections()))
    except Exception as exc:
        return ChromaStatus(reachable=False, error=type(exc).__name__)
