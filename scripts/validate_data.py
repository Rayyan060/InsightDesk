#!/usr/bin/env python
"""Validate Annex C CSV files and write the validation report.

Thin wrapper around app.cli.validate_data so it runs from the repository root without
installing the backend package. Inside the Docker image use:
    docker compose exec backend python -m app.cli.validate_data ...
Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.validate_data import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
