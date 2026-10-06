"""Run the evaluation suite against POST /support: answer-type accuracy,
groundedness/citation precision, tool-use correctness, escalation precision and
recall, refusal behaviour, and latency.

NOT IMPLEMENTED: planned for Phase 7. Exits with status 2 so automation never
mistakes this placeholder for a successful run.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("scripts/evaluate.py is not implemented yet (planned for Phase 7).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
