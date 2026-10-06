#!/usr/bin/env python
"""Validate the knowledge base and Source Register; exits 1 on errors.

Thin wrapper around app.cli.validate_knowledge. Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.validate_knowledge import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
