"""Version-aware precedence rules (Phase 3).

Planned rules (to be confirmed against the participant guide):
1. Only documents effective on or before ``as_of_date`` are eligible.
2. When several versions of the same document are eligible, the latest
   effective version wins; older versions are marked ``superseded``.
3. Explicit ``supersedes`` links override date ordering.
4. Disagreements that the rules cannot resolve are reported as
   ``ConflictRecord`` entries (surfaced in ``conflicts_detected``) and may
   trigger escalation by the policy node.
"""

from __future__ import annotations

from datetime import date

from app.agents.state import RetrievedDocument
from app.core.exceptions import NotImplementedFeatureError
from app.schemas.support import ConflictRecord


def apply_precedence(
    documents: list[RetrievedDocument], *, as_of_date: date | None
) -> tuple[list[RetrievedDocument], list[ConflictRecord]]:
    raise NotImplementedFeatureError("Version precedence", planned_phase="Phase 3")
