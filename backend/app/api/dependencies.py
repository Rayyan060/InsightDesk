"""FastAPI dependencies: settings, resources, DB sessions, trace ID, account context."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AccountContextError, ServiceUnavailableError
from app.core.lifecycle import AppResources
from app.core.logging import get_trace_id as _context_trace_id
from app.core.security import ACCOUNT_ID_HEADER, AccountContext, parse_account_id

logger = logging.getLogger(__name__)


def get_resources(request: Request) -> AppResources:
    return request.app.state.resources


def get_settings_dep(resources: Annotated[AppResources, Depends(get_resources)]) -> Settings:
    return resources.settings


def get_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", None) or _context_trace_id()
    if not trace_id:  # Middleware always sets it; this guards misconfiguration.
        raise RuntimeError("TraceIdMiddleware is not installed.")
    return trace_id


def get_db_session(resources: Annotated[AppResources, Depends(get_resources)]) -> Iterator[Session]:
    """Request-scoped session: commit on success, rollback on any exception."""
    if resources.database is None:
        raise ServiceUnavailableError("Database is not available.")
    with resources.database.session_scope() as session:
        yield session


def get_optional_account_context(
    x_account_id: Annotated[
        str | None,
        Header(
            alias=ACCOUNT_ID_HEADER,
            description="Declared account context (not authentication). 1-64 chars [A-Za-z0-9_-].",
        ),
    ] = None,
) -> AccountContext | None:
    return parse_account_id(x_account_id, source="header")


def require_account_context(
    ctx: Annotated[AccountContext | None, Depends(get_optional_account_context)],
) -> AccountContext:
    if ctx is None:
        raise AccountContextError(f"The {ACCOUNT_ID_HEADER} header is required for this endpoint.")
    return ctx


_retriever_lock = threading.Lock()


def get_retriever(resources: AppResources):
    """ChromaDB retriever if the KB has been ingested; otherwise an in-memory lexical index.

    Built once per app (first call can load the embedding model, so call it from
    a sync route, which FastAPI runs in a worker thread).
    """
    if resources.retriever is not None:
        return resources.retriever
    with _retriever_lock:
        if resources.retriever is None:
            from app.knowledge.documents import read_register
            from app.rag.retriever import chroma_retriever, memory_retriever

            try:
                entries, issues, _ = read_register()
                retriever = chroma_retriever(resources.chroma_client, entries) if resources.chroma_client is not None and entries else None
                if retriever is None:
                    logger.warning("retriever_fallback_memory", extra={"reason": "chroma not configured or KB not ingested"})
                    retriever = memory_retriever()
            except Exception as exc:
                logger.error("retriever_unavailable", extra={"error_type": type(exc).__name__})
                raise ServiceUnavailableError("Knowledge retrieval is not available.") from None
            resources.retriever = retriever
            logger.info("retriever_ready", extra={"backend": retriever.backend})
    return resources.retriever


ResourcesDep = Annotated[AppResources, Depends(get_resources)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
TraceIdDep = Annotated[str, Depends(get_trace_id)]
DbSessionDep = Annotated[Session, Depends(get_db_session)]
OptionalAccountDep = Annotated[AccountContext | None, Depends(get_optional_account_context)]
AccountDep = Annotated[AccountContext, Depends(require_account_context)]
