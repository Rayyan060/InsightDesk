"""Application exception hierarchy and centralized FastAPI exception handlers.

Every error leaving the API uses the same envelope (see
``app.schemas.common.ErrorResponse``)::

    {"error": {"code": "...", "message": "...", "details": [...]}, "trace_id": "..."}

Handlers never echo request bodies or raw input values back to the client, since
those may contain customer PII.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class InsightDeskError(Exception):
    """Base class for errors that map to a structured HTTP response."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class ConfigurationError(InsightDeskError):
    """Raised when settings are missing or invalid. Usually fatal at startup."""

    status_code = 500
    code = "configuration_error"


class BadRequestError(InsightDeskError):
    status_code = 400
    code = "bad_request"


class AccountContextError(BadRequestError):
    """The X-Account-Id header (or body account_id) is malformed or inconsistent."""

    code = "invalid_account_context"


class PayloadTooLargeError(InsightDeskError):
    status_code = 413
    code = "payload_too_large"


class ServiceUnavailableError(InsightDeskError):
    """A required backing component (SQLite, ChromaDB, Ollama) cannot be used."""

    status_code = 503
    code = "service_unavailable"


class NotImplementedFeatureError(InsightDeskError):
    """Endpoint or capability is planned for a later phase.

    Used instead of returning placeholder/fake success responses.
    """

    status_code = 501
    code = "not_implemented"

    def __init__(self, feature: str, *, planned_phase: str | None = None) -> None:
        message = f"{feature} is not implemented yet."
        if planned_phase:
            message += f" Planned for {planned_phase}."
        super().__init__(message)
        self.feature = feature
        self.planned_phase = planned_phase


# ---------------------------------------------------------------------- #
# Response helpers
# ---------------------------------------------------------------------- #
def error_payload(
    code: str,
    message: str,
    *,
    trace_id: str | None,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "error": {"code": code, "message": message, "details": details or []},
        "trace_id": trace_id,
    }


def _trace_id() -> str | None:
    # Imported lazily to avoid a cycle (logging -> exceptions -> logging).
    from app.core.logging import get_trace_id

    return get_trace_id()


def _json_error(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_payload(code, message, trace_id=_trace_id(), details=details),
        headers=headers,
    )


_HTTP_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "too_many_requests",
}


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only location, message and type from validation errors.

    Pydantic includes the rejected ``input`` (and sometimes ``ctx`` with the
    original exception), which can contain customer messages or identifiers.
    Those are deliberately dropped.
    """
    sanitized = []
    for error in errors:
        sanitized.append(
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": str(error.get("msg", "Invalid value")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return sanitized


# ---------------------------------------------------------------------- #
# Handlers
# ---------------------------------------------------------------------- #
async def _insightdesk_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InsightDeskError)
    log = logger.error if exc.status_code >= 500 and exc.status_code != 501 else logger.info
    log(
        "request_failed",
        extra={"error_code": exc.code, "status_code": exc.status_code, "path": request.url.path},
    )
    return _json_error(exc.status_code, exc.code, exc.message, exc.details)


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = sanitize_validation_errors(list(exc.errors()))
    logger.info(
        "request_validation_failed",
        extra={"path": request.url.path, "error_count": len(details)},
    )
    return _json_error(422, "validation_error", "Request validation failed.", details)


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error."
    return _json_error(exc.status_code, code, message, headers=getattr(exc, "headers", None))


def register_exception_handlers(app: FastAPI) -> None:
    """Attach structured handlers.

    Truly unexpected exceptions are handled by ``TraceIdMiddleware`` so that the
    500 response still carries the trace ID header (Starlette's
    ServerErrorMiddleware sits outside user middleware).
    """
    app.add_exception_handler(InsightDeskError, _insightdesk_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
