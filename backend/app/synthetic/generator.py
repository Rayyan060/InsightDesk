"""Synthetic customer-account data: blueprints and the seeded generator.

Pipeline position: ``scenarios`` (what must exist) → ``build_blueprints`` (the
exact invariants) → a filler (seeded RNG here, or the LLM in
``llm_generator``) → ``check_conformance`` → validation.

Everything is driven by one ``random.Random(seed)``, so the same seed,
reference date, reference data and account count give byte-identical output.
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.database.models import RESERVED_ACCOUNT_RANGE
from app.database.repositories.policy_registry import resolve_numeric
from app.database.row_schemas import PlanLimitRow, PolicyRuleRow
from app.synthetic.scenarios import (
    DEFAULT_ACCOUNT_COUNT,
    EDGE_CASE_SPECS,
    FIRST_ACCOUNT_NUMBER,
    FIRST_INVOICE_NUMBER,
    INR_PER_USD,
    PLATFORM_COMPONENTS,
    PRODUCT_VERSIONS,
    AccountSpec,
)

USAGE_METRICS: dict[str, str] = {
    "workflow_runs": "monthly_workflow_runs",
    "api_calls_peak_per_min": "api_rate_limit_per_min",
    "seats_used": "seats",
}
FAILURE_REASONS = ("card_declined", "insufficient_funds", "expired_card", "do_not_honor")

_COMPANY_PREFIXES = (
    "Aster", "Brindle", "Cobaltine", "Dunmore", "Emberly", "Fennel", "Glimmer", "Harborview", "Irisfield",
    "Juniperhill", "Kestrel", "Lumenary", "Marlowe", "Nimbusly", "Orchidia", "Pebblecrest", "Quillon", "Rookery",
    "Sablewood", "Tamarind", "Umberline", "Vesperia", "Willowmere", "Yarrowby", "Zephyrine",
)
_COMPANY_SUFFIXES = (
    "Analytics", "Logistics", "Studios", "Health", "Labs", "Foods", "Robotics", "Media", "Retail", "Finance",
    "Systems", "Works", "Freight", "Clinics",
)
_FIRST_NAMES = (
    "avery", "blake", "casey", "devon", "emery", "finley", "harper", "jordan", "kai", "logan", "morgan", "noor",
    "oakley", "parker", "quinn", "reese", "rowan", "sasha", "taylor", "yuki",
)
_LAST_NAMES = (
    "abara", "bellwether", "castellan", "dunleavy", "eskild", "farrow", "galloway", "hartigan", "ishida",
    "jovan", "kowal", "lindqvist", "moreau", "nakamura", "okafor", "petrova", "quaranta", "ramires",
    "santoro", "thorne",
)


# ---------------------------------------------------------------------- #
# Blueprints: the invariants
# ---------------------------------------------------------------------- #
@dataclass
class InvoiceBlueprint:
    invoice_id: str
    charged_on: date
    amount: float
    currency: str
    status: str  # paid | failed | refunded
    card_last4: str


@dataclass
class UsageBlueprint:
    period: str
    pinned: dict[str, int] = field(default_factory=dict)  # exact values the data must contain
    limits: dict[str, int] = field(default_factory=dict)


@dataclass
class AccountBlueprint:
    spec: AccountSpec
    account_id: str
    plan: str
    status: str
    product_version: str
    currency: str
    created_at: date
    invoices: list[InvoiceBlueprint]
    usage: list[UsageBlueprint]
    reference_date: date

    @property
    def scenario(self) -> str:
        return self.spec.scenario


@dataclass
class GeneratedData:
    rows: dict[str, list[dict[str, Any]]]
    blueprints: list[AccountBlueprint]
    manifest: list[dict[str, str]]
    provenance: dict[str, Any]


def _month_add(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _period(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _price(plan_limits: dict[str, PlanLimitRow], plan: str, currency: str) -> float:
    usd = plan_limits[plan].monthly_price
    return round(usd * INR_PER_USD, 2) if currency == "INR" else float(usd)


def _filler_specs(rng: random.Random, count: int) -> list[AccountSpec]:
    specs = []
    for index in range(count):
        plan = rng.choices(("Free", "Pro", "Business", "Enterprise"), weights=(25, 35, 25, 15))[0]
        if plan == "Free":
            status = rng.choices(("active", "cancelled"), weights=(85, 15))[0]
        else:
            status = rng.choices(("active", "past_due", "suspended", "cancelled"), weights=(72, 10, 6, 12))[0]
        version = rng.choices(PRODUCT_VERSIONS, weights=(45, 20, 15, 10, 7, 3))[0]
        currency = "INR" if plan != "Free" and rng.random() < 0.15 else "USD"
        pattern = {"past_due": "latest_failed", "suspended": "last_two_failed"}.get(status, "monthly")
        specs.append(
            AccountSpec(
                scenario="baseline",
                description=f"Baseline {plan} account ({status})",
                plan=plan,
                status=status,
                product_version=version,
                currency=currency,
                invoice_pattern=pattern,
                cancelled_months_ago=rng.randint(1, 4) if status == "cancelled" else None,
            )
        )
    return specs


def _refund_window(rules: list[PolicyRuleRow], plan: str, reference_date: date) -> int:
    value = resolve_numeric(rules, parameter="refund_window_days", as_of=reference_date, plan=plan)
    if value is None:
        raise ValueError(f"policy registry has no refund_window_days rule for plan {plan}")
    return int(value)


def _billing_day_for(spec: AccountSpec, rules: list[PolicyRuleRow], reference_date: date) -> tuple[int | None, date | None]:
    """Some patterns pin the latest charge to an exact date relative to the reference date."""
    pattern = spec.invoice_pattern
    days_ago: int | None = None
    if pattern == "refund_window_last_day":
        days_ago = _refund_window(rules, spec.plan, reference_date)
    elif pattern == "refund_window_day_after":
        days_ago = _refund_window(rules, spec.plan, reference_date) + 1
    elif pattern.startswith("charged_days_ago:"):
        days_ago = int(pattern.split(":", 1)[1])
    if days_ago is None:
        return spec.billing_day, None
    latest = reference_date - timedelta(days=days_ago)
    if latest.day > 28:
        raise ValueError("pinned charge date falls after the 28th; choose another reference date")
    return latest.day, latest


def build_blueprints(
    *,
    seed: int,
    reference_date: date,
    plan_limits: dict[str, PlanLimitRow],
    policy_rules: list[PolicyRuleRow],
    account_count: int = DEFAULT_ACCOUNT_COUNT,
) -> tuple[list[AccountBlueprint], random.Random]:
    if account_count < len(EDGE_CASE_SPECS):
        raise ValueError(f"account_count must be at least {len(EDGE_CASE_SPECS)} to cover every edge case")
    if FIRST_ACCOUNT_NUMBER + account_count - 1 >= RESERVED_ACCOUNT_RANGE[0]:
        raise ValueError("account_count would reach the judges' reserved account range A9000-A9999")
    rng = random.Random(seed)
    specs = list(EDGE_CASE_SPECS) + _filler_specs(rng, account_count - len(EDGE_CASE_SPECS))
    invoice_number = FIRST_INVOICE_NUMBER
    blueprints: list[AccountBlueprint] = []
    ref_year, ref_month = reference_date.year, reference_date.month

    for index, spec in enumerate(specs):
        account_id = f"A{FIRST_ACCOUNT_NUMBER + index:04d}"
        billing_day, pinned_latest = _billing_day_for(spec, policy_rules, reference_date)

        # --- created_at -------------------------------------------------
        if spec.created_at is not None:
            created = spec.created_at
        else:
            months_back = 4 if spec.invoice_pattern == "upgrade" else rng.randint(4, 30)
            y, m = _month_add(ref_year, ref_month, -months_back)
            day = billing_day or rng.randint(1, 28)
            created = date(y, m, day)
        billing_day = billing_day or min(created.day, 28)

        # --- cancellation boundary --------------------------------------
        cutoff_period = _period(ref_year, ref_month)
        if spec.cancelled_months_ago:
            cy, cm = _month_add(ref_year, ref_month, -spec.cancelled_months_ago)
            cutoff_period = _period(cy, cm)  # no charges or usage from this month on

        # --- invoices ---------------------------------------------------
        card_last4 = f"{rng.randint(0, 9999):04d}"
        invoices: list[InvoiceBlueprint] = []
        if plan_limits[spec.plan].monthly_price > 0:
            charge_dates = []
            y, m = created.year, created.month
            while (y, m) <= (ref_year, ref_month):
                charge = date(y, m, min(billing_day, calendar.monthrange(y, m)[1]))
                in_range = created <= charge <= reference_date
                before_cancellation = not spec.cancelled_months_ago or _period(y, m) < cutoff_period
                if in_range and before_cancellation:
                    charge_dates.append(charge)
                y, m = _month_add(y, m, 1)
            limit = spec.months_billed or rng.randint(2, 5)
            charge_dates = charge_dates[-limit:]
            if pinned_latest is not None and (not charge_dates or charge_dates[-1] != pinned_latest):
                raise AssertionError(f"{spec.scenario}: latest charge is not the pinned date")

            for position, charged_on in enumerate(charge_dates):
                plan_for_charge = spec.plan
                if spec.invoice_pattern == "upgrade" and position < len(charge_dates) - 1:
                    plan_for_charge = spec.upgraded_from or spec.plan
                invoices.append(
                    InvoiceBlueprint(
                        invoice_id=f"INV-{invoice_number:04d}",
                        charged_on=charged_on,
                        amount=_price(plan_limits, plan_for_charge, spec.currency),
                        currency=spec.currency,
                        status="paid",
                        card_last4=card_last4,
                    )
                )
                invoice_number += 1

            if invoices:
                if spec.invoice_pattern == "latest_failed":
                    invoices[-1].status = "failed"
                elif spec.invoice_pattern == "last_two_failed":
                    for inv in invoices[-2:]:
                        inv.status = "failed"
                elif spec.invoice_pattern == "older_refunded":
                    if len(invoices) < 3:
                        raise AssertionError(f"{spec.scenario}: needs at least 3 invoices")
                    invoices[-3].status = "refunded"
                elif spec.invoice_pattern == "duplicate_latest":
                    latest = invoices[-1]
                    invoices.append(
                        InvoiceBlueprint(
                            invoice_id=f"INV-{invoice_number:04d}",
                            charged_on=latest.charged_on,
                            amount=latest.amount,
                            currency=latest.currency,
                            status="paid",
                            card_last4=latest.card_last4,
                        )
                    )
                    invoice_number += 1

        # --- usage periods ----------------------------------------------
        limits = {metric: getattr(plan_limits[spec.plan], column) for metric, column in USAGE_METRICS.items()}
        usage: list[UsageBlueprint] = []
        for back in (2, 1, 0):
            y, m = _month_add(ref_year, ref_month, -back)
            period = _period(y, m)
            before_creation = period < created.strftime("%Y-%m")
            after_cancellation = bool(spec.cancelled_months_ago) and period >= cutoff_period
            if before_creation or after_cancellation:
                continue
            pinned: dict[str, int] = {}
            if back == 0:
                for metric, rule in spec.current_usage.items():
                    kind, amount = rule  # type: ignore[misc]
                    if kind == "ratio":
                        pinned[metric] = int(round(limits[metric] * float(amount)))
                    elif kind == "over":
                        pinned[metric] = limits[metric] + int(amount)
            usage.append(UsageBlueprint(period=period, pinned=pinned, limits=limits))

        blueprints.append(
            AccountBlueprint(
                spec=spec,
                account_id=account_id,
                plan=spec.plan,
                status=spec.status,
                product_version=spec.product_version,
                currency=spec.currency,
                created_at=created,
                invoices=invoices,
                usage=usage,
                reference_date=reference_date,
            )
        )
    return blueprints, rng


# ---------------------------------------------------------------------- #
# Seeded filler
# ---------------------------------------------------------------------- #
def _seeded_usage_value(rng: random.Random, metric: str, limit: int, current: bool, reference_date: date) -> int:
    if metric == "seats_used":
        return rng.randint(1, max(1, int(limit * 0.7)))
    ratio = rng.uniform(0.10, 0.70)
    if metric == "workflow_runs" and current:
        days = calendar.monthrange(reference_date.year, reference_date.month)[1]
        ratio *= reference_date.day / days  # partial month so far
    return int(limit * ratio)


def fill_seeded(blueprints: list[AccountBlueprint], rng: random.Random) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {"accounts": [], "usage": [], "invoices": []}
    used_names: set[str] = set()
    used_emails: set[str] = set()
    for bp in blueprints:
        while True:
            name = f"{rng.choice(_COMPANY_PREFIXES)} {rng.choice(_COMPANY_SUFFIXES)}"
            if name not in used_names:
                used_names.add(name)
                break
        while True:
            email = f"{rng.choice(_FIRST_NAMES)}.{rng.choice(_LAST_NAMES)}@example.com"
            if email not in used_emails:
                used_emails.add(email)
                break
        rows["accounts"].append(
            {
                "account_id": bp.account_id,
                "company_name": name,
                "owner_email": email,
                "plan": bp.plan,
                "status": bp.status,
                "product_version": bp.product_version,
                "created_at": bp.created_at.isoformat(),
            }
        )
        reference_period = bp.reference_date.strftime("%Y-%m")
        for usage in bp.usage:
            values = {}
            for metric in USAGE_METRICS:
                if metric in usage.pinned:
                    values[metric] = usage.pinned[metric]
                else:
                    values[metric] = _seeded_usage_value(
                        rng, metric, usage.limits[metric], usage.period == reference_period, bp.reference_date
                    )
            rows["usage"].append({"account_id": bp.account_id, "period": usage.period, **values})
        for inv in bp.invoices:
            rows["invoices"].append(
                {
                    "invoice_id": inv.invoice_id,
                    "account_id": bp.account_id,
                    "amount": inv.amount,
                    "currency": inv.currency,
                    "charged_on": inv.charged_on.isoformat(),
                    "status": inv.status,
                    "failure_reason": rng.choice(FAILURE_REASONS) if inv.status == "failed" else None,
                    "card_last4": inv.card_last4,
                }
            )
    return rows


def platform_status_rows(reference_date: date, rng: random.Random) -> list[dict[str, Any]]:
    base = datetime.combine(reference_date, time(8, 0), tzinfo=timezone.utc)
    rows = []
    incident = 1004
    for component, status in PLATFORM_COMPONENTS:
        updated = base - timedelta(minutes=rng.randint(5, 600))
        incident_id = None
        if status != "operational":
            incident_id = f"INC-{reference_date.year}-{incident:04d}"
            incident += 1
        rows.append(
            {
                "component": component,
                "status": status,
                "incident_id": incident_id,
                "updated_at": updated.isoformat().replace("+00:00", "Z"),
            }
        )
    return rows


def manifest_rows(blueprints: list[AccountBlueprint]) -> list[dict[str, str]]:
    rows = []
    for bp in blueprints:
        if bp.scenario == "baseline":
            continue
        rows.append(
            {
                "scenario": bp.scenario,
                "account_id": bp.account_id,
                "invoice_ids": ";".join(inv.invoice_id for inv in bp.invoices[-2:]),
                "description": bp.spec.description,
            }
        )
    return rows


def generate_seeded(
    *,
    seed: int,
    reference_date: date,
    plan_limits: dict[str, PlanLimitRow],
    policy_rules: list[PolicyRuleRow],
    account_count: int = DEFAULT_ACCOUNT_COUNT,
) -> GeneratedData:
    blueprints, rng = build_blueprints(
        seed=seed,
        reference_date=reference_date,
        plan_limits=plan_limits,
        policy_rules=policy_rules,
        account_count=account_count,
    )
    rows = fill_seeded(blueprints, rng)
    rows["platform_status"] = platform_status_rows(reference_date, rng)
    return GeneratedData(
        rows=rows,
        blueprints=blueprints,
        manifest=manifest_rows(blueprints),
        provenance={"generator": "seeded", "seed": seed, "reference_date": reference_date.isoformat()},
    )


# ---------------------------------------------------------------------- #
# Conformance: does generated output honour the blueprint?
# ---------------------------------------------------------------------- #
def check_conformance(bp: AccountBlueprint, bundle: dict[str, Any]) -> list[str]:
    """Return human-readable deviations of a generated bundle from its blueprint.

    Used for LLM output (feedback for retries, and the "what the LLM got wrong"
    log) and as a self-check on the seeded generator.
    """
    problems: list[str] = []
    account = bundle.get("account") or {}
    for column, expected in (
        ("account_id", bp.account_id),
        ("plan", bp.plan),
        ("status", bp.status),
        ("product_version", bp.product_version),
        ("created_at", bp.created_at.isoformat()),
    ):
        if str(account.get(column, "")).strip() != expected:
            problems.append(f"account.{column} must be exactly {expected!r}")

    usage_rows = {str(u.get("period")): u for u in bundle.get("usage") or [] if isinstance(u, dict)}
    expected_periods = [u.period for u in bp.usage]
    if sorted(usage_rows) != sorted(expected_periods):
        problems.append(f"usage must contain exactly the periods {expected_periods}")
    for usage in bp.usage:
        row = usage_rows.get(usage.period)
        if row is None:
            continue
        for metric, value in usage.pinned.items():
            if row.get(metric) != value:
                problems.append(f"usage {usage.period}.{metric} must be exactly {value}")
        for metric, limit in usage.limits.items():
            if metric not in usage.pinned and isinstance(row.get(metric), int) and row[metric] >= limit:
                problems.append(f"usage {usage.period}.{metric} must stay below the plan limit {limit}")

    invoices = {str(i.get("invoice_id")): i for i in bundle.get("invoices") or [] if isinstance(i, dict)}
    expected_ids = [inv.invoice_id for inv in bp.invoices]
    if sorted(invoices) != sorted(expected_ids):
        problems.append(f"invoices must use exactly the invoice IDs {expected_ids}")
    for inv in bp.invoices:
        row = invoices.get(inv.invoice_id)
        if row is None:
            continue
        for column, expected in (
            ("charged_on", inv.charged_on.isoformat()),
            ("status", inv.status),
            ("currency", inv.currency),
            ("card_last4", inv.card_last4),
        ):
            if str(row.get(column, "")).strip() != expected:
                problems.append(f"invoice {inv.invoice_id}.{column} must be exactly {expected!r}")
        try:
            if abs(float(row.get("amount")) - inv.amount) > 1e-9:
                problems.append(f"invoice {inv.invoice_id}.amount must be exactly {inv.amount}")
        except (TypeError, ValueError):
            problems.append(f"invoice {inv.invoice_id}.amount must be a number")
        if inv.status == "failed" and not row.get("failure_reason"):
            problems.append(f"invoice {inv.invoice_id} is failed and needs a failure_reason")
        if inv.status != "failed" and row.get("failure_reason"):
            problems.append(f"invoice {inv.invoice_id} is not failed, so failure_reason must be null")
    return problems
