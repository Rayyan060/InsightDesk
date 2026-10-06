"""Dataset validation: schema, referential integrity and business consistency.

Three layers:

1. **Schema** (``validate_raw_rows``): every row is parsed with the Annex C
   row models in ``app.database.row_schemas``, and primary keys must be unique.
2. **Referential** (``check_referential``): ``usage`` and ``invoices`` must
   reference known accounts.
3. **Business** (``check_business_rules``): the logical constraints from
   Section 4.2 of the guide ("amounts positive; only card last-4 stored;
   statuses consistent with invoices") plus our own date and consistency
   rules, each with a stable rule code.

For our own synthetic data, every violation is an *error*. For judge-supplied
data loaded through the CSV loader, business rules are reported as *warnings*:
judges' data follows their own logic, and our interpretation of "consistent"
must never block their accounts. Rules 1 and 2 always stay errors.

Issues never contain PII values: only table, rule, row number or primary key,
and column.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.database.models import (
    RESERVED_ACCOUNT_RANGE,
    RESERVED_INVOICE_PREFIX,
    RESERVED_SOURCE_PREFIX,
)
from app.database.row_schemas import (
    PRIMARY_KEYS,
    ROW_MODELS,
    AccountRow,
    InvoiceRow,
    PlanLimitRow,
    PlatformStatusRow,
    PolicyRuleRow,
    UsageRow,
)

Severity = Literal["error", "warning"]
Dataset = dict[str, list[Any]]  # table name -> list of row models

NUMERIC_OPERATORS = ("<", "<=", ">", ">=")


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    table: str
    message: str
    row: int | None = None  # 1-based data row (CSV line = row + 1) when known
    key: str | None = None  # primary key of the offending record (never PII)
    column: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def primary_key(table: str, row: BaseModel) -> str:
    return "|".join(str(getattr(row, col)) for col in PRIMARY_KEYS[table])


# ---------------------------------------------------------------------- #
# 1. Schema
# ---------------------------------------------------------------------- #
def validation_issues(table: str, exc: ValidationError, row: int | None, key: str | None) -> list[Issue]:
    issues = []
    for err in exc.errors(include_input=False, include_url=False, include_context=False):
        column = ".".join(str(part) for part in err.get("loc", ())) or None
        message = err.get("msg", "invalid value")
        if message.startswith("Value error, "):
            message = message[len("Value error, ") :]
        issues.append(
            Issue("error", "schema", table, message, row=row, key=key, column=column)
        )
    return issues


def validate_raw_rows(raw: dict[str, list[dict[str, Any]]]) -> tuple[Dataset, list[Issue]]:
    """Parse raw dict rows into row models; report schema and duplicate-key errors."""
    dataset: Dataset = {}
    issues: list[Issue] = []
    for table, rows in raw.items():
        model = ROW_MODELS[table]
        seen: set[str] = set()
        parsed = []
        for index, values in enumerate(rows, start=1):
            try:
                row = model.model_validate(values)
            except ValidationError as exc:
                issues.extend(validation_issues(table, exc, index, None))
                continue
            key = primary_key(table, row)
            if key in seen:
                issues.append(Issue("error", "duplicate_key", table, "duplicate primary key", row=index, key=key))
                continue
            seen.add(key)
            parsed.append(row)
        dataset[table] = parsed
    return dataset, issues


# ---------------------------------------------------------------------- #
# 2. Referential
# ---------------------------------------------------------------------- #
def check_referential(dataset: Dataset, known_account_ids: set[str] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    accounts = {a.account_id for a in dataset.get("accounts", [])} | (known_account_ids or set())
    for table in ("usage", "invoices"):
        for row in dataset.get(table, []):
            if row.account_id not in accounts:
                issues.append(
                    Issue(
                        "error",
                        "foreign_key",
                        table,
                        "account_id references an account that does not exist",
                        key=primary_key(table, row),
                        column="account_id",
                    )
                )
    plans = {p.plan for p in dataset.get("plan_limits", [])}
    if plans:
        for account in dataset.get("accounts", []):
            if account.plan not in plans:
                issues.append(
                    Issue(
                        "warning",
                        "plan_without_limits",
                        "accounts",
                        "plan has no row in plan_limits",
                        key=account.account_id,
                        column="plan",
                    )
                )
    return issues


# ---------------------------------------------------------------------- #
# 3. Business rules
# ---------------------------------------------------------------------- #
def is_reserved_account_id(account_id: str) -> bool:
    try:
        number = int(account_id[1:])
    except ValueError:
        return False
    low, high = RESERVED_ACCOUNT_RANGE
    return account_id.startswith("A") and low <= number <= high


def is_reserved_invoice_id(invoice_id: str) -> bool:
    return invoice_id.upper().startswith(RESERVED_INVOICE_PREFIX)


def is_reserved_source_id(source_id: str) -> bool:
    return source_id.upper().startswith(RESERVED_SOURCE_PREFIX)


def check_reserved_identifiers(dataset: Dataset) -> list[Issue]:
    """Our own data must not use identifiers reserved for judges (Annex C)."""
    issues = []
    for account in dataset.get("accounts", []):
        if is_reserved_account_id(account.account_id):
            issues.append(Issue("error", "reserved_id", "accounts", "account_id is in the judges' reserved range A9000-A9999", key=account.account_id))
    for table in ("usage", "invoices"):
        for row in dataset.get(table, []):
            if is_reserved_account_id(row.account_id):
                issues.append(Issue("error", "reserved_id", table, "account_id is in the judges' reserved range A9000-A9999", key=primary_key(table, row)))
    for invoice in dataset.get("invoices", []):
        if is_reserved_invoice_id(invoice.invoice_id):
            issues.append(Issue("error", "reserved_id", "invoices", "invoice_id uses the judges' reserved prefix INV-J", key=invoice.invoice_id))
    for rule in dataset.get("policy_registry", []):
        if is_reserved_source_id(rule.source_id):
            issues.append(Issue("error", "reserved_id", "policy_registry", "source_id uses the judges' reserved prefix JD-", key=rule.rule_id))
    return issues


def _latest_invoice(invoices: list[InvoiceRow]) -> InvoiceRow | None:
    if not invoices:
        return None
    return max(invoices, key=lambda inv: (inv.charged_on, inv.invoice_id))


def check_business_rules(
    dataset: Dataset,
    *,
    reference_date: date,
    severity: Severity = "error",
    known_source_ids: set[str] | None = None,
) -> list[Issue]:
    """Logical consistency checks. ``severity`` applies to all consistency rules."""
    issues: list[Issue] = []

    def add(code: str, table: str, message: str, key: str | None, column: str | None = None, level: Severity | None = None) -> None:
        issues.append(Issue(level or severity, code, table, message, key=key, column=column))

    accounts: list[AccountRow] = dataset.get("accounts", [])
    invoices_by_account: dict[str, list[InvoiceRow]] = defaultdict(list)
    for invoice in dataset.get("invoices", []):
        invoices_by_account[invoice.account_id].append(invoice)
    usage_by_account: dict[str, list[UsageRow]] = defaultdict(list)
    for usage in dataset.get("usage", []):
        usage_by_account[usage.account_id].append(usage)

    reference_period = reference_date.strftime("%Y-%m")
    created_by_account = {a.account_id: a.created_at for a in accounts}

    for account in accounts:
        aid = account.account_id
        account_invoices = invoices_by_account.get(aid, [])
        latest = _latest_invoice(account_invoices)

        if date.fromisoformat(account.created_at) > reference_date:
            add("future_date", "accounts", "created_at is after the reference date", aid, "created_at")

        # Statuses consistent with invoices (Section 4.2).
        if account.status == "past_due" and (latest is None or latest.status != "failed"):
            add("status_vs_invoices", "accounts", "past_due account's latest invoice is not failed", aid, "status")
        if account.status == "suspended" and (latest is None or latest.status != "failed"):
            add("status_vs_invoices", "accounts", "suspended account's latest invoice is not failed", aid, "status")
        if account.status == "active" and latest is not None and latest.status == "failed":
            add("status_vs_invoices", "accounts", "active account's latest invoice is failed (should be past_due or suspended)", aid, "status")
        if account.status == "cancelled":
            current = [u for u in usage_by_account.get(aid, []) if u.period == reference_period and u.workflow_runs > 0]
            if current:
                add("status_vs_usage", "accounts", "cancelled account has workflow runs in the reference period", aid, "status")

        if account.plan == "Free":
            recent_cutoff = (reference_date - timedelta(days=31)).isoformat()
            if any(inv.charged_on >= recent_cutoff for inv in account_invoices):
                add("free_plan_billed", "accounts", "Free plan account was charged in the last 31 days", aid, "plan")

        currencies = {inv.currency for inv in account_invoices}
        if len(currencies) > 1:
            add("mixed_currency", "invoices", "account is billed in more than one currency", aid, "currency", level="warning")

    for invoice in dataset.get("invoices", []):
        created = created_by_account.get(invoice.account_id)
        if created and invoice.charged_on < created:
            add("charge_before_creation", "invoices", "charged_on is before the account's created_at", invoice.invoice_id, "charged_on")
        if date.fromisoformat(invoice.charged_on) > reference_date:
            add("future_date", "invoices", "charged_on is after the reference date", invoice.invoice_id, "charged_on")
        if invoice.status == "failed" and not invoice.failure_reason:
            add("failed_without_reason", "invoices", "failed invoice has no failure_reason", invoice.invoice_id, "failure_reason", level="warning")

    for usage in dataset.get("usage", []):
        key = primary_key("usage", usage)
        if usage.period > reference_period:
            add("future_date", "usage", "period is after the reference month", key, "period")
        created = created_by_account.get(usage.account_id)
        if created and usage.period < created[:7]:
            add("usage_before_creation", "usage", "period is before the account's creation month", key, "period")

    for component in dataset.get("platform_status", []):
        if component.status != "operational" and not component.incident_id:
            add("incident_missing", "platform_status", "non-operational component has no incident_id", component.component, "incident_id", level="warning")

    rules = dataset.get("policy_registry", [])
    for rule in rules:
        issues.extend(_check_policy_rule(rule, known_source_ids))
    if rules and known_source_ids is None:
        issues.append(
            Issue(
                "warning",
                "policy_source_unverified",
                "policy_registry",
                f"source_id of {len(rules)} rules not checked: no source register available yet "
                "(the policy articles are written with the knowledge base in Phase 3)",
                column="source_id",
            )
        )
    return issues


def _check_policy_rule(rule: PolicyRuleRow, known_source_ids: set[str] | None) -> list[Issue]:
    issues = []
    if rule.operator in NUMERIC_OPERATORS and rule.value != "plan_limit":
        try:
            float(rule.value)
        except ValueError:
            issues.append(Issue("error", "policy_value", "policy_registry", "comparison operator requires a numeric value", key=rule.rule_id, column="value"))
    if known_source_ids is not None and rule.source_id not in known_source_ids:
        issues.append(Issue("error", "policy_source_missing", "policy_registry", "source_id is not in the source register", key=rule.rule_id, column="source_id"))
    return issues


def check_policy_registry_conflicts(rules: list[PolicyRuleRow]) -> list[Issue]:
    """Two rules for the same parameter, plan scope and effective date are ambiguous."""
    issues = []
    seen: dict[tuple[str, str, str], str] = {}
    for rule in rules:
        scopes = ["ALL"] if rule.scope_plans == "ALL" else rule.scope_plans.split(";")
        for scope in scopes:
            key = (rule.parameter, scope, rule.effective_from)
            if key in seen and rule.parameter not in {"escalate_on_intent"}:
                issues.append(Issue("error", "policy_ambiguous", "policy_registry", f"same parameter, plan and effective date as {seen[key]}", key=rule.rule_id))
            seen.setdefault(key, rule.rule_id)
    return issues


def summarize(issues: list[Issue]) -> dict[str, int]:
    counts: dict[str, int] = {"error": 0, "warning": 0}
    for issue in issues:
        counts[issue.severity] += 1
    return counts


__all__ = [
    "AccountRow",
    "Dataset",
    "InvoiceRow",
    "Issue",
    "PlanLimitRow",
    "PlatformStatusRow",
    "PolicyRuleRow",
    "UsageRow",
    "check_business_rules",
    "check_policy_registry_conflicts",
    "check_referential",
    "check_reserved_identifiers",
    "has_errors",
    "is_reserved_account_id",
    "is_reserved_invoice_id",
    "is_reserved_source_id",
    "primary_key",
    "summarize",
    "validate_raw_rows",
    "validation_issues",
]
