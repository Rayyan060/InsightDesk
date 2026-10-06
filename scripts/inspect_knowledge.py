#!/usr/bin/env python
"""Inspect knowledge sources, applicability by version/date, or export retrieval-ready section records.

Thin wrapper around app.cli.inspect_knowledge. Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.inspect_knowledge import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
