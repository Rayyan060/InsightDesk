#!/usr/bin/env python
"""Load Annex C CSV files (for example judge test accounts) into SQLite: python scripts/load_accounts.py --dir test_accounts/

Thin wrapper around app.cli.load_accounts so it runs from the repository root without
installing the backend package. Inside the Docker image use:
    docker compose exec backend python -m app.cli.load_accounts ...
Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.load_accounts import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
