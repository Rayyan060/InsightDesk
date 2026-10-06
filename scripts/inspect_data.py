#!/usr/bin/env python
"""Inspect or export the dataset in the database or a CSV directory (emails masked).

Thin wrapper around app.cli.inspect_data so it runs from the repository root without
installing the backend package. Inside the Docker image use:
    docker compose exec backend python -m app.cli.inspect_data ...
Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.inspect_data import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
