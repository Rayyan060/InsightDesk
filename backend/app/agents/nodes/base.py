"""Node interface shared by all graph nodes.

A node is a callable ``(AgentState) -> dict`` returning a *partial* state
update. ``audited_node`` wraps a node to append an ``AuditEvent`` with timing
and outcome, so audit coverage does not depend on each node remembering to
record itself.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from app.agents.state import AgentState, AuditEvent

logger = logging.getLogger("insightdesk.agent")

NodeUpdate = dict[str, Any]


class GraphNode(Protocol):
    __name__: str

    def __call__(self, state: AgentState) -> NodeUpdate: ...


class NodeNotImplementedError(NotImplementedError):
    """Raised by node stubs that belong to a later phase."""

    def __init__(self, node: str, planned_phase: str) -> None:
        super().__init__(f"Graph node '{node}' is not implemented yet (planned for {planned_phase}).")
        self.node = node
        self.planned_phase = planned_phase


def audited_node(name: str) -> Callable[[Callable[[AgentState], NodeUpdate]], GraphNode]:
    def decorator(fn: Callable[[AgentState], NodeUpdate]) -> GraphNode:
        @functools.wraps(fn)
        def wrapper(state: AgentState) -> NodeUpdate:
            started_at = datetime.now(timezone.utc)
            started = time.perf_counter()
            try:
                update = fn(state)
            except Exception as exc:
                logger.warning("node_failed", extra={"node": name, "error_type": type(exc).__name__})
                raise
            event = AuditEvent(
                node=name,
                started_at=started_at,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                outcome="ok",
            )
            update = dict(update)
            update["audit_events"] = [*update.get("audit_events", []), event]
            return update

        wrapper.__name__ = name
        return wrapper  # type: ignore[return-value]

    return decorator
