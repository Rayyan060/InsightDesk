"""Policy registry: loading, coverage of Annex A topics, effective dating, read-only access."""

from __future__ import annotations

import inspect
from datetime import date

import pytest

from app.database.init_db import initialize_database
from app.database.repositories.policy_registry import PolicyRegistryRepository, resolve_numeric, select_active_rules
from app.database.validation import check_policy_registry_conflicts, is_reserved_source_id
from app.tools.registry import TOOL_SPECS


def test_reference_registry_loads_into_sqlite(db) -> None:
    report = initialize_database(db)
    assert report.ok and report.reference_import.tables["policy_registry"].inserted == 23
    with db.session_scope() as session:
        rules = PolicyRegistryRepository(session).all_rules()
    assert len(rules) == 23


@pytest.mark.parametrize(
    ("topic", "predicate"),
    [
        ("refund eligibility", lambda r: r.parameter in {"refund_window_days", "refundable_invoice_status", "refund_requires_human_approval"}),
        ("billing disputes", lambda r: r.parameter == "escalate_on_intent" and "billing_dispute" in r.value),
        ("account deletion", lambda r: "account_deletion" in r.value),
        ("security incidents", lambda r: "security_incident" in r.value),
        ("human escalation", lambda r: r.parameter in {"escalate_on_explicit_human_request", "repeated_contact_min"}),
        ("tool failures", lambda r: r.parameter == "required_tool_failures"),
        ("low groundedness", lambda r: r.parameter == "critic_min_groundedness"),
        ("escalation SLAs", lambda r: r.parameter.endswith(("_first_response_hours", "_first_response_business_days"))),
    ],
)
def test_annex_a_topics_covered(reference_data, topic, predicate) -> None:
    _, rules = reference_data
    assert any(predicate(r) for r in rules), topic


def test_every_rule_cites_a_policy_article(reference_data) -> None:
    _, rules = reference_data
    for rule in rules:
        assert rule.source_id.startswith("KB-POL-") and rule.source_section, rule.rule_id
        assert not is_reserved_source_id(rule.source_id)


def test_no_ambiguous_rules(reference_data) -> None:
    _, rules = reference_data
    assert check_policy_registry_conflicts(rules) == []


def test_effective_dates_and_plan_scope(reference_data) -> None:
    _, rules = reference_data
    window = lambda plan, day: resolve_numeric(rules, parameter="refund_window_days", as_of=day, plan=plan)  # noqa: E731
    assert window("Pro", date(2026, 10, 6)) == 14
    assert window("Business", date(2026, 10, 31)) == 14
    assert window("Pro", date(2026, 11, 1)) == 7  # REFUND-WINDOW-03 from its effective date
    assert window("Enterprise", date(2026, 11, 1)) == 30
    assert window("Free", date(2026, 10, 6)) is None  # Free is never charged
    groundedness = select_active_rules(rules, parameter="critic_min_groundedness", as_of=date(2026, 10, 6), plan="Pro")
    assert [r.rule_id for r in groundedness] == ["GROUNDEDNESS-01"]
    assert select_active_rules(rules, parameter="critic_min_groundedness", as_of=date(2025, 12, 31), plan="Pro") == []


def test_r4_registry_matches_config(reference_data) -> None:
    _, rules = reference_data
    from app.core.config import load_settings

    revisions = resolve_numeric(rules, parameter="max_critic_revisions", as_of=date(2026, 10, 6), plan=None)
    assert revisions == load_settings(_env_file=None).max_critic_revisions == 1


def test_policy_rules_cannot_be_modified_at_request_time() -> None:
    public = {name for name, _ in inspect.getmembers(PolicyRegistryRepository, inspect.isfunction) if not name.startswith("_")}
    assert public == {"all_rules", "get", "active_rules"}  # read-only
    assert all("policy_registry" not in spec.writes for spec in TOOL_SPECS.values())
