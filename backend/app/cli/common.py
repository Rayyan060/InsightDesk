"""Shared helpers for the command-line tools."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from app.core.config import PROJECT_ROOT, load_settings
from app.core.exceptions import ConfigurationError
from app.core.logging import configure_logging


def setup_logging(verbose: bool) -> None:
    configure_logging("INFO" if verbose else "WARNING", "text")


def resolve_db_url(db: str | None) -> str:
    """``--db`` accepts a file path or a sqlite URL; default is DATABASE_URL."""
    if db:
        if db.startswith("sqlite:"):
            return db
        path = Path(db)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return f"sqlite:///{path.as_posix()}"
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        raise SystemExit(f"error: {exc}") from None
    if settings.resolved_database_url is None:
        raise SystemExit("error: DATABASE_URL is not set; pass --db")
    return settings.resolved_database_url


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def out(text: str = "") -> None:
    sys.stdout.write(text + "\n")


__all__ = ["PROJECT_ROOT", "mask_email", "out", "parse_date", "project_path", "resolve_db_url", "setup_logging"]
