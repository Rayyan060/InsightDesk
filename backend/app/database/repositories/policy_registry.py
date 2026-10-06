"""Read-only access to the policy registry.

The application never writes policy rules at request time: this repository
has no mutating methods, and no tool or agent node can create or change
rules. Rules are only loaded by the operator CLI (``init_db`` /
``load_accounts``) from reviewed CSV files.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import PolicyRule
from app.database.row_schemas import PolicyRuleRow


def rule_applies_to_plan(rule: PolicyRuleRow, plan: str | None) -> bool:
    if rule.scope_plans == "ALL":
        return True
    return plan is not None and plan in rule.scope_plans.split(";")


def select_active_rules(
    rules: Iterable[PolicyRuleRow], *, parameter: str, as_of: date, plan: str | None = None
) -> list[PolicyRuleRow]:
    """Rules for ``parameter`` in effect on ``as_of`` for ``plan``.

    Among rules for the same parameter and plan scope, the one with the latest
    ``effective_from`` on or before ``as_of`` wins (recency within the same
    authority, Annex A.2 step 4). Rules with different scopes are all returned,
    most specific first.
    """
    candidates = [
        r
        for r in rules
        if r.parameter == parameter
        and date.fromisoformat(r.effective_from) <= as_of
        and rule_applies_to_plan(r, plan)
    ]
    latest_by_scope: dict[str, PolicyRuleRow] = {}
    for rule in sorted(candidates, key=lambda r: (r.effective_from, r.rule_id)):
        latest_by_scope[rule.scope_plans] = rule
    return sorted(latest_by_scope.values(), key=lambda r: (r.scope_plans == "ALL", r.rule_id))


def resolve_numeric(rules: Iterable[PolicyRuleRow], *, parameter: str, as_of: date, plan: str | None) -> float | None:
    """Value of the most specific active rule, or None if no rule applies."""
    active = select_active_rules(rules, parameter=parameter, as_of=as_of, plan=plan)
    return float(active[0].value) if active else None


class PolicyRegistryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def all_rules(self) -> list[PolicyRuleRow]:
        rows = self.session.execute(select(PolicyRule).order_by(PolicyRule.rule_id)).scalars()
        return [PolicyRuleRow.model_validate(r, from_attributes=True) for r in rows]

    def get(self, rule_id: str) -> PolicyRuleRow | None:
        row = self.session.get(PolicyRule, rule_id)
        return PolicyRuleRow.model_validate(row, from_attributes=True) if row else None

    def active_rules(self, *, parameter: str, as_of: date, plan: str | None = None) -> list[PolicyRuleRow]:
        stmt = select(PolicyRule).where(PolicyRule.parameter == parameter)
        rows = [PolicyRuleRow.model_validate(r, from_attributes=True) for r in self.session.execute(stmt).scalars()]
        return select_active_rules(rows, parameter=parameter, as_of=as_of, plan=plan)
