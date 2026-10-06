"""Structured logging with trace-ID correlation and PII/secret redaction.

* Every record gets the current request's ``trace_id`` (from a context var set
  by ``TraceIdMiddleware``).
* Output is JSON (default) or a single-line text format.
* All messages, ``extra`` fields and exception text pass through
  ``app.core.security.redact``/``scrub_text`` before being written. Sensitive
  keys (``message``, ``account_id``, ``password`` ...) are dropped entirely.

Callers should still avoid logging raw customer content; redaction is a safety
net, not a licence.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any

from app.core.security import redact, scrub_text

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)

# Attributes present on every LogRecord; anything else came from ``extra=``.
_STANDARD_ATTRS = frozenset(
    vars(logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None)).keys()
) | {"message", "asctime", "trace_id", "taskName", "color_message"}  # color_message: uvicorn ANSI duplicate

_HANDLER_NAME = "insightdesk"


def get_trace_id() -> str | None:
    return _trace_id_var.get()


def set_trace_id(trace_id: str | None) -> Token[str | None]:
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: Token[str | None]) -> None:
    _trace_id_var.reset(token)


class TraceIdFilter(logging.Filter):
    """Attach the current trace ID to each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_text(record.getMessage()),
            "trace_id": getattr(record, "trace_id", None),
        }
        extras = _extras(record)
        if extras:
            payload["context"] = redact(extras)
        if record.exc_info:
            payload["exception"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


class RedactingTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        line = (
            f"{timestamp} {record.levelname:<8} {record.name} "
            f"[trace={getattr(record, 'trace_id', None) or '-'}] {scrub_text(record.getMessage())}"
        )
        extras = _extras(record)
        if extras:
            line += " " + json.dumps(redact(extras), default=str, ensure_ascii=False)
        if record.exc_info:
            line += "\n" + scrub_text(self.formatException(record.exc_info))
        return line


def build_handler(log_format: str = "json", stream: Any = None) -> logging.Handler:
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.set_name(_HANDLER_NAME)
    handler.addFilter(TraceIdFilter())
    handler.setFormatter(RedactingJsonFormatter() if log_format == "json" else RedactingTextFormatter())
    return handler


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Install the redacting handler on the root logger (idempotent).

    Uvicorn's loggers are routed through the same handler. Uvicorn's access
    log is silenced because it records full URLs including query strings and
    client addresses; ``TraceIdMiddleware`` emits a sanitized request log
    instead.
    """
    root = logging.getLogger()
    for existing in list(root.handlers):
        if existing.get_name() == _HANDLER_NAME:
            root.removeHandler(existing)
    root.addHandler(build_handler(log_format))
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True

    # Third-party libraries that are chatty or log full request URLs
    # (including query strings) at INFO.
    for noisy in ("httpx", "httpx2", "httpcore", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))
