#!/usr/bin/env python
"""Generate, validate, export and verify the synthetic customer dataset (seeded or LLM).

Thin wrapper around app.cli.generate_data so it runs from the repository root without
installing the backend package. Inside the Docker image use:
    docker compose exec backend python -m app.cli.generate_data ...
Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.generate_data import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
