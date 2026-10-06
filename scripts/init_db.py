#!/usr/bin/env python
"""Create the Annex C schema and load reference data (idempotent, never drops data).

Thin wrapper around app.cli.init_db so it runs from the repository root without
installing the backend package. Inside the Docker image use:
    docker compose exec backend python -m app.cli.init_db ...
Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.init_db import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
