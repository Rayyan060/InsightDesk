"""Application resource lifecycle (startup/shutdown).

Added beyond the prescribed layout to keep ``main.py`` small: it owns the
long-lived resources (SQLite engine, Chroma client, Ollama HTTP client) that
are created in the FastAPI lifespan and stored on ``app.state.resources``.

Startup never fails because an optional backing service is down. The failure
is logged and surfaced by ``GET /health`` as ``unavailable``. Invalid
*configuration* still fails fast, in ``load_settings``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.database.connection import Database
from app.database.init_db import DEFAULT_REFERENCE_DIR, initialize_database
from app.services.llm import OllamaClient

logger = logging.getLogger(__name__)


@dataclass
class AppResources:
    settings: Settings
    database: Database | None = None
    database_error: str | None = None
    chroma_client: Any | None = None
    chroma_error: str | None = None
    ollama: OllamaClient | None = None
    retriever: Any | None = None  # built lazily on first /support call (see api.dependencies.get_retriever)


def startup(settings: Settings) -> AppResources:
    resources = AppResources(settings=settings)

    db_url = settings.resolved_database_url
    if db_url is None:
        logger.warning("database_not_configured")
    else:
        try:
            database = Database(db_url, echo=False)
            init = initialize_database(
                database, reference_dir=DEFAULT_REFERENCE_DIR if settings.seed_reference_data else None
            )
            resources.database = database
            if init.schema_problems:
                logger.error("database_schema_mismatch", extra={"problem_count": len(init.schema_problems)})
            elif init.reference_import is not None:
                logger.info(
                    "reference_data_loaded",
                    extra={t: r.inserted for t, r in init.reference_import.tables.items()},
                )
            logger.info("database_ready")
        except Exception as exc:
            resources.database_error = type(exc).__name__
            logger.error("database_init_failed", extra={"error_type": type(exc).__name__})

    chroma_dir = settings.resolved_chroma_dir
    if chroma_dir is None:
        logger.warning("chroma_not_configured")
    else:
        try:
            from app.rag.vector_store import open_chroma_client

            resources.chroma_client = open_chroma_client(chroma_dir)
            logger.info("chroma_ready")
        except ImportError:
            resources.chroma_error = "chromadb package is not installed"
            logger.error("chroma_init_failed", extra={"error_type": "ImportError"})
        except Exception as exc:
            resources.chroma_error = type(exc).__name__
            logger.error("chroma_init_failed", extra={"error_type": type(exc).__name__})

    if settings.ollama_base_url is None:
        logger.warning("ollama_not_configured")
    else:
        resources.ollama = OllamaClient(
            settings.ollama_base_url,
            settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )

    return resources


async def shutdown(resources: AppResources) -> None:
    if resources.ollama is not None:
        await resources.ollama.aclose()
    if resources.database is not None:
        resources.database.dispose()
    logger.info("shutdown_complete")
