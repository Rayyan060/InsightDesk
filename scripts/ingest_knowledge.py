#!/usr/bin/env python
"""Ingest the validated knowledge base into ChromaDB (idempotent).

Thin wrapper around app.cli.ingest_knowledge. Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.ingest_knowledge import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
