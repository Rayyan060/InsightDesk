"""Annex C transcribed as data, independent of the ORM models.

``verify_schema`` compares a live SQLite database against this transcription.
It is used by the init script, by ``/health`` and by the schema tests, so a
drift between the ORM models and the official schema is caught rather than
silently shipped.

Extra columns and tables are allowed (the guide says "You may add more");
missing, renamed or retyped required columns, and wrong PK/FK, are not.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    type: str  # TEXT | INTEGER | REAL
    pk: bool = False
    fk: str | None = None  # "table.column"


ANNEX_C_SCHEMA: dict[str, tuple[ColumnSpec, ...]] = {
    "accounts": (
        ColumnSpec("account_id", "TEXT", pk=True),
        ColumnSpec("company_name", "TEXT"),
        ColumnSpec("owner_email", "TEXT"),
        ColumnSpec("plan", "TEXT"),
        ColumnSpec("status", "TEXT"),
        ColumnSpec("product_version", "TEXT"),
        ColumnSpec("created_at", "TEXT"),
    ),
    "plan_limits": (
        ColumnSpec("plan", "TEXT", pk=True),
        ColumnSpec("api_rate_limit_per_min", "INTEGER"),
        ColumnSpec("monthly_workflow_runs", "INTEGER"),
        ColumnSpec("seats", "INTEGER"),
        ColumnSpec("support_tier", "TEXT"),
        ColumnSpec("monthly_price", "REAL"),
    ),
    "usage": (
        ColumnSpec("account_id", "TEXT", pk=True, fk="accounts.account_id"),
        ColumnSpec("period", "TEXT", pk=True),
        ColumnSpec("workflow_runs", "INTEGER"),
        ColumnSpec("api_calls_peak_per_min", "INTEGER"),
        ColumnSpec("seats_used", "INTEGER"),
    ),
    "invoices": (
        ColumnSpec("invoice_id", "TEXT", pk=True),
        ColumnSpec("account_id", "TEXT", fk="accounts.account_id"),
        ColumnSpec("amount", "REAL"),
        ColumnSpec("currency", "TEXT"),
        ColumnSpec("charged_on", "TEXT"),
        ColumnSpec("status", "TEXT"),
        ColumnSpec("failure_reason", "TEXT"),
        ColumnSpec("card_last4", "TEXT"),
    ),
    "platform_status": (
        ColumnSpec("component", "TEXT", pk=True),
        ColumnSpec("status", "TEXT"),
        ColumnSpec("incident_id", "TEXT"),
        ColumnSpec("updated_at", "TEXT"),
    ),
    "policy_registry": (
        ColumnSpec("rule_id", "TEXT", pk=True),
        ColumnSpec("description", "TEXT"),
        ColumnSpec("parameter", "TEXT"),
        ColumnSpec("operator", "TEXT"),
        ColumnSpec("value", "TEXT"),
        ColumnSpec("scope_plans", "TEXT"),
        ColumnSpec("effective_from", "TEXT"),
        ColumnSpec("source_id", "TEXT"),
        ColumnSpec("source_section", "TEXT"),
    ),
    "handoffs": (
        ColumnSpec("handoff_id", "TEXT", pk=True),
        ColumnSpec("conversation_id", "TEXT"),
        ColumnSpec("account_id", "TEXT"),
        ColumnSpec("queue", "TEXT"),
        ColumnSpec("priority", "TEXT"),
        ColumnSpec("created_at", "TEXT"),
        ColumnSpec("bundle_json", "TEXT"),
    ),
}


def verify_schema(engine: Engine) -> list[str]:
    """Return human-readable schema problems (empty list means conformant)."""
    problems: list[str] = []
    with engine.connect() as conn:
        tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        for table, specs in ANNEX_C_SCHEMA.items():
            if table not in tables:
                problems.append(f"{table}: table missing")
                continue
            # Table names come from the constant above, never from user input.
            info = {r[1]: r for r in conn.execute(text(f'PRAGMA table_info("{table}")'))}
            fks = {
                r[3]: f"{r[2]}.{r[4]}" for r in conn.execute(text(f'PRAGMA foreign_key_list("{table}")'))
            }
            for spec in specs:
                column = info.get(spec.name)
                if column is None:
                    problems.append(f"{table}.{spec.name}: column missing")
                    continue
                declared = (column[2] or "").upper()
                if declared != spec.type:
                    problems.append(f"{table}.{spec.name}: type {declared or 'none'}, expected {spec.type}")
                if bool(column[5]) != spec.pk:
                    problems.append(f"{table}.{spec.name}: primary-key flag mismatch")
                if spec.fk and fks.get(spec.name) != spec.fk:
                    problems.append(f"{table}.{spec.name}: expected foreign key to {spec.fk}")
    return problems
