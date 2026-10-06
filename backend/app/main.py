"""FastAPI application entry point.

Run locally (from ``backend/``)::

    uvicorn app.main:app --reload

``create_app`` is a factory so tests can build isolated apps with their own
settings; the module-level ``app`` uses environment configuration.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.lifecycle import shutdown, startup
from app.core.logging import configure_logging
from app.core.middleware import RequestSizeLimitMiddleware, TraceIdMiddleware
from app.core.security import ACCOUNT_ID_HEADER, TRACE_ID_HEADER

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "startup",
            extra={"app_env": settings.app_env, "version": __version__, "ollama_model": settings.ollama_model},
        )
        app.state.resources = startup(settings)
        try:
            yield
        finally:
            await shutdown(app.state.resources)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "InsightDesk: agentic AI customer support (HCLTech Future Ready AI Engineer "
            "Hackathon, Use Case 2). Phase 1 foundation: endpoints other than /health "
            "return HTTP 501 until implemented."
        ),
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Middleware: the last one added is the outermost.
    # Order of execution: TraceId -> CORS -> RequestSizeLimit -> routes.
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", ACCOUNT_ID_HEADER, TRACE_ID_HEADER],
        expose_headers=[TRACE_ID_HEADER],
    )
    app.add_middleware(TraceIdMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
