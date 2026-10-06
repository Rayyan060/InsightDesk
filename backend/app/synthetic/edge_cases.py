"""Data-driven verification of the required edge cases and coverage.

Each check is a predicate over one account's records. A case passes only if:

* the account the manifest assigns to it really satisfies the predicate; and
* at least one account in the dataset satisfies it.

So a generator bug (or an LLM that "forgot" a boundary) shows up as a
failure, never as an unverified claim.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from app.database.models import ACCOUNT_STATUSES, INVOICE_STATUSES, PLANS
from app.database.repositories.policy_registry import resolve_numeric
from app.database.row_schemas import AccountRow, InvoiceRow, PlanLimitRow, PolicyRuleRow, UsageRow
from app.database.validation import Dataset
from app.synthetic.generator import USAGE_METRICS
from app.synthetic.scenarios import CURRENT_VERSION, INR_PER_USD, REQUIRED_EDGE_CASES


@dataclass
class AccountView:
    account: AccountRow
    invoices: list[InvoiceRow]
    current: UsageRow | None
    limits: PlanLimitRow


@dataclass
class EdgeCaseResult:
    case: str
    passed: bool
    manifest_account: str | None
    satisfied_by: list[str] = field(default_factory=list)
    detail: str = ""


def _ratio(view: AccountView, metric: str) -> float | None:
    if view.current is None:
        return None
    limit = getattr(view.limits, USAGE_METRICS[metric])
    return getattr(view.current, metric) / limit if limit else None


def _metric_equals(metric: str, offset: int) -> Callable[[AccountView, dict], bool]:
    def predicate(view: AccountView, _: dict) -> bool:
        if view.current is None:
            return False
        return getattr(view.current, metric) == getattr(view.limits, USAGE_METRICS[metric]) + offset

    return predicate


def _within_quota(view: AccountView, _: dict) -> bool:
    ratios = [_ratio(view, m) for m in USAGE_METRICS]
    return view.account.status == "active" and all(r is not None and r < 0.8 for r in ratios)


def _approaching(view: AccountView, _: dict) -> bool:
    ratios = [_ratio(view, m) for m in USAGE_METRICS]
    if any(r is None for r in ratios):
        return False
    return any(0.8 <= r < 1.0 for r in ratios) and all(r <= 1.0 for r in ratios)  # type: ignore[operator]


def _latest(invoices: list[InvoiceRow]) -> InvoiceRow | None:
    return max(invoices, key=lambda i: (i.charged_on, i.invoice_id)) if invoices else None


def _failed_payment(view: AccountView, _: dict) -> bool:
    latest = _latest(view.invoices)
    return view.account.status == "past_due" and latest is not None and latest.status == "failed" and bool(latest.failure_reason)


def _duplicate(view: AccountView, _: dict) -> bool:
    seen = set()
    for inv in view.invoices:
        key = (inv.charged_on, inv.amount, inv.currency)
        if inv.status == "paid" and key in seen:
            return True
        if inv.status == "paid":
            seen.add(key)
    return False


def _refund_offset(offset: int) -> Callable[[AccountView, dict], bool]:
    def predicate(view: AccountView, ctx: dict) -> bool:
        paid = [i for i in view.invoices if i.status == "paid"]
        latest = _latest(paid)
        window = resolve_numeric(ctx["rules"], parameter="refund_window_days", as_of=ctx["reference_date"], plan=view.account.plan)
        if latest is None or window is None:
            return False
        return (ctx["reference_date"] - date.fromisoformat(latest.charged_on)).days == int(window) + offset

    return predicate


def _recently_upgraded(view: AccountView, ctx: dict) -> bool:
    latest = _latest(view.invoices)
    if latest is None or len(view.invoices) < 2:
        return False
    factor = INR_PER_USD if latest.currency == "INR" else 1.0
    prices = {plan: round(limit.monthly_price * factor, 2) for plan, limit in ctx["plan_limits"].items()}
    current_price = prices[view.account.plan]
    cheaper = {p for p in prices.values() if 0 < p < current_price}
    recent = (ctx["reference_date"] - date.fromisoformat(latest.charged_on)).days <= 31
    earlier = [i for i in view.invoices if i.invoice_id != latest.invoice_id]
    return recent and abs(latest.amount - current_price) < 1e-9 and any(i.amount in cheaper for i in earlier)


def _older_version(view: AccountView, _: dict) -> bool:
    return int(view.account.product_version.split(".")[0]) < int(CURRENT_VERSION.split(".")[0])


PREDICATES: dict[str, Callable[[AccountView, dict], bool]] = {
    "active_within_quota": _within_quota,
    "approaching_quota": _approaching,
    "workflow_runs_at_limit": _metric_equals("workflow_runs", 0),
    "workflow_runs_one_over": _metric_equals("workflow_runs", 1),
    "api_rate_at_limit": _metric_equals("api_calls_peak_per_min", 0),
    "api_rate_one_over": _metric_equals("api_calls_peak_per_min", 1),
    "failed_payment": _failed_payment,
    "suspended_account": lambda v, _: v.account.status == "suspended",
    "duplicate_charge": _duplicate,
    "refund_last_day_of_window": _refund_offset(0),
    "refund_one_day_after_window": _refund_offset(1),
    "no_invoices": lambda v, _: not v.invoices,
    "multiple_invoices": lambda v, _: len(v.invoices) >= 3,
    "recently_upgraded": _recently_upgraded,
    "older_product_version": _older_version,
}
assert set(PREDICATES) == set(REQUIRED_EDGE_CASES)


def verify_edge_cases(
    dataset: Dataset,
    manifest: list[dict[str, str]],
    *,
    plan_limits: dict[str, PlanLimitRow],
    policy_rules: list[PolicyRuleRow],
    reference_date: date,
) -> list[EdgeCaseResult]:
    invoices: dict[str, list[InvoiceRow]] = defaultdict(list)
    for inv in dataset.get("invoices", []):
        invoices[inv.account_id].append(inv)
    reference_period = reference_date.strftime("%Y-%m")
    current = {u.account_id: u for u in dataset.get("usage", []) if u.period == reference_period}
    views = {
        a.account_id: AccountView(a, invoices.get(a.account_id, []), current.get(a.account_id), plan_limits[a.plan])
        for a in dataset.get("accounts", [])
    }
    ctx = {"rules": policy_rules, "reference_date": reference_date, "plan_limits": plan_limits}
    assigned = {row["scenario"]: row["account_id"] for row in manifest}

    results: list[EdgeCaseResult] = []
    for case in REQUIRED_EDGE_CASES:
        predicate = PREDICATES[case]
        satisfied = sorted(aid for aid, view in views.items() if predicate(view, ctx))
        manifest_account = assigned.get(case)
        manifest_ok = manifest_account is None or manifest_account in satisfied
        passed = bool(satisfied) and manifest_ok
        detail = "" if passed else (
            "no account satisfies this case" if not satisfied else f"manifest account {manifest_account} does not satisfy it"
        )
        results.append(EdgeCaseResult(case, passed, manifest_account, satisfied, detail))

    accounts = dataset.get("accounts", [])
    for case, required, actual in (
        ("coverage_all_plans", set(PLANS), {a.plan for a in accounts}),
        ("coverage_all_statuses", set(ACCOUNT_STATUSES), {a.status for a in accounts}),
    ):
        missing = sorted(required - actual)
        results.append(EdgeCaseResult(case, not missing, None, sorted(actual), f"missing: {missing}" if missing else ""))
    invoice_statuses = {i.status for i in dataset.get("invoices", [])}
    missing_statuses = sorted(set(INVOICE_STATUSES) - invoice_statuses)
    results.append(
        EdgeCaseResult(
            "coverage_all_invoice_statuses", not missing_statuses, None, sorted(invoice_statuses),
            f"missing: {missing_statuses}" if missing_statuses else "",
        )
    )
    versions = sorted({a.product_version for a in accounts})
    results.append(EdgeCaseResult("coverage_multiple_versions", len(versions) >= 3, None, versions, "" if len(versions) >= 3 else "fewer than 3 product versions"))
    results.append(
        EdgeCaseResult("coverage_min_30_accounts", len(accounts) >= 30, None, [str(len(accounts))], "" if len(accounts) >= 30 else "fewer than 30 accounts")
    )
    return results
