"""LLM-based generation of the synthetic account data (guide Section 4.2).

Per account:

1. Render the verbatim prompt template (``data/synthetic/prompts``) with the
   account's blueprint. Invariants are marked FIXED; realism fields are FREE.
2. Call the model with Ollama's structured output (``format`` = JSON schema of
   ``AccountBundle``), at low temperature with a fixed seed.
3. Enforce the schema: parse the JSON and validate with the Annex C row models.
4. Check conformance with the blueprint (``check_conformance``).
5. On any failure, retry (up to ``max_attempts``), feeding back the exact
   problems. If it still fails, either fall back to the seeded filler for that
   account (recorded as such) or abort, depending on ``fallback``.

Every attempt is logged (model, options, prompt hash, tokens, latency,
outcome, problems) for the data card's "What the LLM got wrong" section.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from string import Template
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.database.row_schemas import AccountRow, InvoiceRow, PlanLimitRow, PlatformStatusRow, PolicyRuleRow, UsageRow
from app.synthetic.generator import (
    USAGE_METRICS,
    AccountBlueprint,
    GeneratedData,
    build_blueprints,
    check_conformance,
    fill_seeded,
    manifest_rows,
    platform_status_rows,
)
from app.synthetic.scenarios import DEFAULT_ACCOUNT_COUNT, PLATFORM_COMPONENTS

PROMPT_VERSION = "v1"


class AccountBundle(BaseModel):
    account: AccountRow
    usage: list[UsageRow]
    invoices: list[InvoiceRow]


class PlatformStatusBundle(BaseModel):
    rows: list[PlatformStatusRow]


@dataclass
class LLMReply:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None


class JsonLLM(Protocol):
    model: str

    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any], *, temperature: float, seed: int) -> LLMReply: ...


class OllamaJsonLLM:
    """Minimal Ollama ``/api/chat`` client using structured (JSON-schema) output."""

    def __init__(self, base_url: str, model: str, *, timeout_seconds: float = 120.0) -> None:
        self.model = model
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def chat_json(self, messages, schema, *, temperature, seed):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = self._client.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "format": schema,
                "stream": False,
                "options": {"temperature": temperature, "seed": seed},
            },
        )
        response.raise_for_status()
        payload = response.json()
        return LLMReply(
            text=payload.get("message", {}).get("content", ""),
            prompt_tokens=payload.get("prompt_eval_count"),
            completion_tokens=payload.get("eval_count"),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    def close(self) -> None:
        self._client.close()


@dataclass
class AttemptLog:
    target: str  # account_id or "platform_status"
    attempt: int
    outcome: Literal["accepted", "invalid_json", "schema_error", "conformance_error", "call_failed"]
    problems: list[str] = field(default_factory=list)
    prompt_sha256: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None


@dataclass
class LLMRunSummary:
    model: str
    temperature: float
    seed: int
    prompt_version: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    accepted_first_try: int = 0
    accepted_after_retry: int = 0
    fell_back_to_seeded: list[str] = field(default_factory=list)
    attempts: list[AttemptLog] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["attempts"] = [asdict(a) for a in self.attempts]
        return data


class LLMGenerationError(RuntimeError):
    pass


def _load_prompt(prompts_dir: Path, name: str) -> str:
    return (prompts_dir / f"{name}_{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def _usage_lines(bp: AccountBlueprint) -> str:
    lines = []
    for usage in bp.usage:
        parts = [f"period {usage.period} (FIXED)"]
        for metric in USAGE_METRICS:
            limit = usage.limits[metric]
            if metric in usage.pinned:
                parts.append(f"{metric} = {usage.pinned[metric]} (FIXED)")
            else:
                parts.append(f"{metric}: FREE integer between 0 and {max(0, limit - 1)}")
        lines.append("- " + "; ".join(parts))
    return "\n".join(lines) or "- (no usage rows: return an empty list)"


def _invoice_lines(bp: AccountBlueprint) -> str:
    lines = []
    for inv in bp.invoices:
        reason = "failure_reason: FREE snake_case code" if inv.status == "failed" else "failure_reason: null"
        lines.append(
            f"- invoice_id {inv.invoice_id}; account_id {bp.account_id}; amount {inv.amount}; currency {inv.currency}; "
            f"charged_on {inv.charged_on.isoformat()}; status {inv.status}; card_last4 \"{inv.card_last4}\"; {reason}"
        )
    return "\n".join(lines) or "- (no invoices: return an empty list)"


def render_account_prompt(template: str, bp: AccountBlueprint, plan_limit: PlanLimitRow) -> str:
    return Template(template).substitute(
        reference_date=bp.reference_date.isoformat(),
        scenario=bp.scenario,
        description=bp.spec.description,
        account_id=bp.account_id,
        plan=bp.plan,
        status=bp.status,
        product_version=bp.product_version,
        created_at=bp.created_at.isoformat(),
        plan_limits=json.dumps(plan_limit.model_dump()),
        usage_lines=_usage_lines(bp),
        invoice_lines=_invoice_lines(bp),
    )


def _bundle_to_rows(bundle: AccountBundle) -> dict[str, list[dict[str, Any]]]:
    return {
        "accounts": [bundle.account.model_dump()],
        "usage": [u.model_dump() for u in bundle.usage],
        "invoices": [i.model_dump() for i in bundle.invoices],
    }


def _ask(
    llm: JsonLLM,
    *,
    target: str,
    system: str,
    user: str,
    schema_model: type[BaseModel],
    conformance,  # Callable[[dict], list[str]]
    temperature: float,
    seed: int,
    max_attempts: int,
    summary: LLMRunSummary,
) -> BaseModel | None:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    schema = schema_model.model_json_schema()
    prompt_hash = hashlib.sha256((system + "\n" + user).encode()).hexdigest()
    for attempt in range(1, max_attempts + 1):
        log = AttemptLog(target=target, attempt=attempt, outcome="accepted", prompt_sha256=prompt_hash)
        summary.attempts.append(log)
        summary.calls += 1
        try:
            reply = llm.chat_json(messages, schema, temperature=temperature, seed=seed + attempt)
        except (httpx.HTTPError, OSError) as exc:
            log.outcome, log.problems = "call_failed", [type(exc).__name__]
            continue
        log.prompt_tokens, log.completion_tokens, log.latency_ms = reply.prompt_tokens, reply.completion_tokens, reply.latency_ms
        summary.prompt_tokens += reply.prompt_tokens or 0
        summary.completion_tokens += reply.completion_tokens or 0

        problems: list[str]
        try:
            raw = json.loads(reply.text)
        except json.JSONDecodeError:
            log.outcome, problems = "invalid_json", ["output was not valid JSON"]
        else:
            try:
                parsed = schema_model.model_validate(raw)
            except ValidationError as exc:
                log.outcome = "schema_error"
                problems = [
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors(include_input=False, include_url=False)
                ]
            else:
                problems = conformance(raw)
                if not problems:
                    if attempt == 1:
                        summary.accepted_first_try += 1
                    else:
                        summary.accepted_after_retry += 1
                    return parsed
                log.outcome = "conformance_error"
        log.problems = problems
        messages = messages + [
            {"role": "assistant", "content": reply.text},
            {
                "role": "user",
                "content": "Your previous output had these problems:\n- "
                + "\n- ".join(problems[:20])
                + "\nReturn the corrected JSON object only.",
            },
        ]
    return None


def generate_with_llm(
    llm: JsonLLM,
    *,
    seed: int,
    reference_date: date,
    plan_limits: dict[str, PlanLimitRow],
    policy_rules: list[PolicyRuleRow],
    prompts_dir: Path,
    account_count: int = DEFAULT_ACCOUNT_COUNT,
    temperature: float = 0.2,
    max_attempts: int = 3,
    fallback: Literal["seeded", "fail"] = "seeded",
) -> tuple[GeneratedData, LLMRunSummary]:
    blueprints, rng = build_blueprints(
        seed=seed, reference_date=reference_date, plan_limits=plan_limits, policy_rules=policy_rules, account_count=account_count
    )
    summary = LLMRunSummary(model=llm.model, temperature=temperature, seed=seed, prompt_version=PROMPT_VERSION)
    system = _load_prompt(prompts_dir, "accounts_system")
    template = _load_prompt(prompts_dir, "account_bundle")
    rows: dict[str, list[dict[str, Any]]] = {"accounts": [], "usage": [], "invoices": []}
    seen_emails: set[str] = set()

    for index, bp in enumerate(blueprints):
        user = render_account_prompt(template, bp, plan_limits[bp.plan])

        def conformance(raw: dict[str, Any], bp: AccountBlueprint = bp) -> list[str]:
            problems = check_conformance(bp, raw)
            email = str((raw.get("account") or {}).get("owner_email", "")).lower()
            if email in seen_emails:
                problems.append("owner_email is already used by another account; choose a different one")
            return problems

        bundle = _ask(
            llm, target=bp.account_id, system=system, user=user, schema_model=AccountBundle,
            conformance=conformance, temperature=temperature, seed=seed + index * 10, max_attempts=max_attempts, summary=summary,
        )
        if bundle is None:
            if fallback == "fail":
                raise LLMGenerationError(f"LLM output for {bp.account_id} failed validation after {max_attempts} attempts")
            summary.fell_back_to_seeded.append(bp.account_id)
            seeded = fill_seeded([bp], random.Random(seed + index))
            for table, table_rows in seeded.items():
                rows[table].extend(table_rows)
            seen_emails.add(seeded["accounts"][0]["owner_email"].lower())
            continue
        assert isinstance(bundle, AccountBundle)
        seen_emails.add(bundle.account.owner_email.lower())
        for table, table_rows in _bundle_to_rows(bundle).items():
            rows[table].extend(table_rows)

    # Platform status
    fixed_rows = platform_status_rows(reference_date, rng)
    lines = "\n".join(
        f"- component {r['component']} (FIXED); status {r['status']} (FIXED); incident_id "
        + (f"{r['incident_id']} (FIXED)" if r["incident_id"] else "null")
        for r in fixed_rows
    )
    platform_user = Template(_load_prompt(prompts_dir, "platform_status")).substitute(
        reference_date=reference_date.isoformat(), component_lines=lines
    )

    def platform_conformance(raw: dict[str, Any]) -> list[str]:
        got = [(r.get("component"), r.get("status"), r.get("incident_id")) for r in raw.get("rows", [])]
        want = [(r["component"], r["status"], r["incident_id"]) for r in fixed_rows]
        return [] if got == want else [f"rows must be exactly (component, status, incident_id) = {want}"]

    platform = _ask(
        llm, target="platform_status", system=_load_prompt(prompts_dir, "platform_status_system"), user=platform_user,
        schema_model=PlatformStatusBundle, conformance=platform_conformance, temperature=temperature, seed=seed,
        max_attempts=max_attempts, summary=summary,
    )
    if platform is None:
        if fallback == "fail":
            raise LLMGenerationError("LLM platform_status output failed validation")
        summary.fell_back_to_seeded.append("platform_status")
        rows["platform_status"] = fixed_rows
    else:
        assert isinstance(platform, PlatformStatusBundle)
        rows["platform_status"] = [r.model_dump() for r in platform.rows]

    provenance = {
        "generator": "llm",
        "model": llm.model,
        "temperature": temperature,
        "seed": seed,
        "prompt_version": PROMPT_VERSION,
        "reference_date": reference_date.isoformat(),
        "platform_components": [c for c, _ in PLATFORM_COMPONENTS],
    }
    return GeneratedData(rows=rows, blueprints=blueprints, manifest=manifest_rows(blueprints), provenance=provenance), summary
