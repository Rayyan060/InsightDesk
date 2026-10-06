"""Pure-ASGI middleware: trace IDs, request logging, body-size limits.

Pure ASGI (rather than ``BaseHTTPMiddleware``) is used so the trace-ID context
variable reliably propagates into route handlers and background work, and so
unhandled errors can be converted into a structured 500 that still carries the
``X-Trace-Id`` header.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import PayloadTooLargeError, error_payload
from app.core.logging import reset_trace_id, set_trace_id
from app.core.security import TRACE_ID_HEADER

logger = logging.getLogger("insightdesk.request")

# Accept inbound trace IDs only in a safe, bounded format (prevents log injection).
_INBOUND_TRACE_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_TRACE_HEADER_BYTES = TRACE_ID_HEADER.lower().encode("latin-1")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            try:
                return value.decode("latin-1")
            except UnicodeDecodeError:
                return None
    return None


async def _send_json(send: Send, status: int, body: dict[str, Any], trace_id: str) -> None:
    raw = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(raw)).encode()),
                (_TRACE_HEADER_BYTES, trace_id.encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": raw})


class TraceIdMiddleware:
    """Assigns a trace ID per request, logs a sanitized summary, catches crashes.

    A well-formed inbound ``X-Trace-Id`` is reused (for correlation across the
    frontend and backend); anything else is replaced with a fresh UUID4 hex.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = _header(scope, _TRACE_HEADER_BYTES)
        trace_id = inbound if inbound and _INBOUND_TRACE_RE.fullmatch(inbound) else new_trace_id()
        scope.setdefault("state", {})["trace_id"] = trace_id
        token = set_trace_id(trace_id)

        status_code = 500
        response_started = False
        started = time.perf_counter()

        async def send_with_trace(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != _TRACE_HEADER_BYTES
                ]
                headers.append((_TRACE_HEADER_BYTES, trace_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        except Exception:
            logger.exception("unhandled_exception", extra={"path": scope.get("path")})
            if not response_started:
                status_code = 500
                await _send_json(
                    send,
                    500,
                    error_payload("internal_error", "An unexpected error occurred.", trace_id=trace_id),
                    trace_id,
                )
        finally:
            # Path only: query strings may carry identifiers. Bodies are never logged.
            logger.info(
                "request_completed",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            reset_trace_id(token)


class RequestSizeLimitMiddleware:
    """Rejects request bodies larger than ``max_bytes`` with HTTP 413.

    * With ``Content-Length``: rejected up front; the ASGI server guarantees
      the body does not exceed the declared length.
    * Without it (chunked transfer): the body is buffered here, up to the
      limit, and replayed to the app. Raising from ``receive`` instead would
      not work, because FastAPI converts body-read errors into a generic 400.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, scope: Scope, send: Send) -> None:
        trace_id = scope.get("state", {}).get("trace_id") or new_trace_id()
        await _send_json(
            send,
            413,
            error_payload(
                PayloadTooLargeError.code,
                f"Request body exceeds the {self.max_bytes}-byte limit.",
                trace_id=trace_id,
            ),
            trace_id,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _header(scope, b"content-length")
        if declared is not None:
            try:
                too_large = int(declared) > self.max_bytes
            except ValueError:
                too_large = False
            if too_large:
                await self._reject(scope, send)
                return
            await self.app(scope, receive, send)
            return

        if scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return  # client went away; nothing to respond to
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._reject(scope, send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)
