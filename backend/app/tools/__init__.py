"""Deterministic tools over SQLite and the policy registry (R7, Annex C).

Use ``app.tools.registry.invoke_tool``; it validates arguments, enforces
account scoping and records the invocation. Business logic lands in Phase 5.
Until then every tool reports ``not_implemented`` instead of fabricating data.
"""
