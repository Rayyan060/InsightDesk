#!/usr/bin/env python
"""Generate the CloudFlow knowledge base and Source Register (seeded or LLM), then validate it.

Thin wrapper around app.cli.generate_knowledge. Run with --help for options.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli.generate_knowledge import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
