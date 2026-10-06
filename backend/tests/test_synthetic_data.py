"""Synthetic data: reproducibility, reserved IDs, edge cases, pipeline, LLM path."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from app.database.validation import is_reserved_account_id, is_reserved_invoice_id, validate_raw_rows
from app.synthetic.edge_cases import verify_edge_cases
from app.synthetic.generator import build_blueprints, check_conformance, generate_seeded
from app.synthetic.llm_generator import AccountBundle, LLMGenerationError, LLMReply, generate_with_llm
from app.synthetic.pipeline import PROMPTS_DIR, run_pipeline, validate_synthetic_dataset
from app.synthetic.scenarios import DEFAULT_REFERENCE_DATE, DEFAULT_SEED, REQUIRED_EDGE_CASES


def _dataset(generated, reference_data):
    plan_limits, rules = reference_data
    raw = dict(generated.rows, plan_limits=[p.model_dump() for p in plan_limits.values()], policy_registry=[r.model_dump() for r in rules])
    dataset, issues = validate_raw_rows(raw)
    assert not issues, issues
    return dataset


# --- reproducibility ---------------------------------------------------------------
def test_same_seed_same_data(reference_data) -> None:
    plan_limits, rules = reference_data
    kwargs = dict(seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE, plan_limits=plan_limits, policy_rules=rules)
    assert generate_seeded(**kwargs).rows == generate_seeded(**kwargs).rows


def test_different_seed_different_data_same_guarantees(reference_data) -> None:
    plan_limits, rules = reference_data
    a = generate_seeded(seed=1, reference_date=DEFAULT_REFERENCE_DATE, plan_limits=plan_limits, policy_rules=rules)
    b = generate_seeded(seed=2, reference_date=DEFAULT_REFERENCE_DATE, plan_limits=plan_limits, policy_rules=rules)
    assert a.rows["accounts"] != b.rows["accounts"]
    for generated in (a, b):
        issues, edge = validate_synthetic_dataset(
            _dataset(generated, reference_data), generated.manifest, plan_limits=plan_limits, policy_rules=rules, reference_date=DEFAULT_REFERENCE_DATE
        )
        assert not [i for i in issues if i.severity == "error"]
        assert all(e.passed for e in edge)


# --- requirements ---------------------------------------------------------------------
def test_minimum_coverage(seeded_data) -> None:
    accounts = seeded_data.rows["accounts"]
    assert len(accounts) >= 30
    assert {a["plan"] for a in accounts} == {"Free", "Pro", "Business", "Enterprise"}
    assert {a["status"] for a in accounts} == {"active", "past_due", "suspended", "cancelled"}
    assert len({a["product_version"] for a in accounts}) >= 3


def test_no_reserved_identifiers(seeded_data) -> None:
    assert not any(is_reserved_account_id(a["account_id"]) for a in seeded_data.rows["accounts"])
    assert not any(is_reserved_invoice_id(i["invoice_id"]) for i in seeded_data.rows["invoices"])
    assert all(re.fullmatch(r"A\d{4}", a["account_id"]) for a in seeded_data.rows["accounts"])


def test_account_count_cannot_reach_reserved_range(reference_data) -> None:
    plan_limits, rules = reference_data
    with pytest.raises(ValueError, match="reserved"):
        build_blueprints(seed=1, reference_date=DEFAULT_REFERENCE_DATE, plan_limits=plan_limits, policy_rules=rules, account_count=8000)


def test_only_fictional_example_com_emails_and_last4(seeded_data) -> None:
    assert all(a["owner_email"].endswith("@example.com") for a in seeded_data.rows["accounts"])
    assert all(re.fullmatch(r"\d{4}", i["card_last4"]) for i in seeded_data.rows["invoices"])


def test_all_required_edge_cases_verified_from_data(seeded_data, reference_data) -> None:
    plan_limits, rules = reference_data
    results = verify_edge_cases(
        _dataset(seeded_data, reference_data), seeded_data.manifest, plan_limits=plan_limits, policy_rules=rules, reference_date=DEFAULT_REFERENCE_DATE
    )
    by_case = {r.case: r for r in results}
    assert set(REQUIRED_EDGE_CASES) <= set(by_case)
    assert all(r.passed for r in results), [r for r in results if not r.passed]


def test_edge_case_boundaries_are_exact(seeded_data, reference_data) -> None:
    plan_limits, _ = reference_data
    manifest = {m["scenario"]: m["account_id"] for m in seeded_data.manifest}
    current = {u["account_id"]: u for u in seeded_data.rows["usage"] if u["period"] == "2026-10"}
    plan_of = {a["account_id"]: a["plan"] for a in seeded_data.rows["accounts"]}
    at, over = manifest["workflow_runs_at_limit"], manifest["workflow_runs_one_over"]
    assert current[at]["workflow_runs"] == plan_limits[plan_of[at]].monthly_workflow_runs
    assert current[over]["workflow_runs"] == plan_limits[plan_of[over]].monthly_workflow_runs + 1

    invoices = seeded_data.rows["invoices"]
    last_day = max(i["charged_on"] for i in invoices if i["account_id"] == manifest["refund_last_day_of_window"])
    day_after = max(i["charged_on"] for i in invoices if i["account_id"] == manifest["refund_one_day_after_window"])
    assert (DEFAULT_REFERENCE_DATE - date.fromisoformat(last_day)).days == 14  # REFUND-WINDOW-01
    assert (DEFAULT_REFERENCE_DATE - date.fromisoformat(day_after)).days == 15
    dup = [i for i in invoices if i["account_id"] == manifest["duplicate_charge"]]
    assert len({(i["charged_on"], i["amount"]) for i in dup}) < len(dup)


def test_edge_case_verification_catches_a_broken_dataset(seeded_data, reference_data) -> None:
    plan_limits, rules = reference_data
    at = {m["scenario"]: m["account_id"] for m in seeded_data.manifest}["workflow_runs_at_limit"]
    rows = json.loads(json.dumps(seeded_data.rows))
    for u in rows["usage"]:
        if u["account_id"] == at and u["period"] == "2026-10":
            u["workflow_runs"] -= 1
    broken = type(seeded_data)(rows=rows, blueprints=seeded_data.blueprints, manifest=seeded_data.manifest, provenance={})
    results = {r.case: r for r in verify_edge_cases(_dataset(broken, reference_data), seeded_data.manifest,
                                                      plan_limits=plan_limits, policy_rules=rules, reference_date=DEFAULT_REFERENCE_DATE)}
    assert not results["workflow_runs_at_limit"].passed


def test_refund_edges_follow_policy_effective_dates(reference_data) -> None:
    """After 2026-11-01 REFUND-WINDOW-03 (7 days) applies, and the generator adapts."""
    plan_limits, rules = reference_data
    ref = date(2026, 11, 25)
    generated = generate_seeded(seed=DEFAULT_SEED, reference_date=ref, plan_limits=plan_limits, policy_rules=rules)
    manifest = {m["scenario"]: m["account_id"] for m in generated.manifest}
    last = max(i["charged_on"] for i in generated.rows["invoices"] if i["account_id"] == manifest["refund_last_day_of_window"])
    assert (ref - date.fromisoformat(last)).days == 7


def test_seeded_output_conforms_to_blueprints(seeded_data) -> None:
    for bp in seeded_data.blueprints:
        bundle = {
            "account": next(a for a in seeded_data.rows["accounts"] if a["account_id"] == bp.account_id),
            "usage": [u for u in seeded_data.rows["usage"] if u["account_id"] == bp.account_id],
            "invoices": [i for i in seeded_data.rows["invoices"] if i["account_id"] == bp.account_id],
        }
        assert check_conformance(bp, bundle) == [], bp.account_id


# --- pipeline -------------------------------------------------------------------------
def test_pipeline_end_to_end_and_no_overwrite(tmp_path) -> None:
    out = tmp_path / "synthetic"
    result = run_pipeline(out_dir=out, seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE, account_count=36)
    assert result.ok, [s for s in result.steps if not s.ok]
    assert [s.name for s in result.steps] == [
        "generate", "validate_schema", "validate_business", "export_csv", "import_sqlite", "verify_row_counts", "write_report",
    ]
    for name in ("accounts.csv", "usage.csv", "invoices.csv", "platform_status.csv", "edge_cases.csv",
                 "validation_report.md", "validation_report.json", "generation_manifest.json"):
        assert (out / name).exists(), name
    assert result.counts["expected"] == {k: v for k, v in result.counts["database"].items() if k in result.counts["expected"]}

    again = run_pipeline(out_dir=out, seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE, account_count=36)
    assert not again.ok and again.steps[0].name == "preflight"


def test_seeded_pipeline_output_is_byte_deterministic(tmp_path) -> None:
    """The seeded generator itself is deterministic: two runs with the same seed write identical bytes.

    Independent of the committed dataset, which comes from an LLM run (see
    test_committed_dataset_is_reproducible).
    """
    for name in ("a", "b"):
        assert run_pipeline(out_dir=tmp_path / name, seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE, account_count=36).ok
    for name in ("accounts.csv", "usage.csv", "invoices.csv", "platform_status.csv", "edge_cases.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_committed_dataset_is_reproducible(tmp_path) -> None:
    """data/synthetic (the dataset of record) is reproducible according to its recorded provenance.

    A seeded run must regenerate byte-for-byte. An LLM run must agree with its
    manifest and attempt log. Its deterministic parts (edge-case manifest, CSV
    headers, every seeded-fallback account) must be byte-identical, and every
    LLM-filled account must honour every FIXED blueprint value. See
    ``tests/provenance_checks.py``; mutation tests are in ``test_provenance_hardening.py``.
    """
    from provenance_checks import verify_synthetic

    from app.synthetic.pipeline import SYNTHETIC_DIR

    verify_synthetic(SYNTHETIC_DIR, tmp_path)


# --- LLM path (fake model) ---------------------------------------------------------
class FakeLLM:
    """Returns schema-valid bundles taken from the seeded generator, optionally misbehaving first."""

    model = "fake-llm:1"

    def __init__(self, seeded, faults: list[str] | None = None, always_wrong: bool = False) -> None:
        self.seeded = seeded
        self.faults = list(faults or [])
        self.always_wrong = always_wrong
        self.calls: list[list[dict]] = []

    def chat_json(self, messages, schema, *, temperature, seed):
        self.calls.append(messages)
        user = messages[1]["content"]
        if "component" in user and "account_id" not in user:
            return LLMReply(json.dumps({"rows": self.seeded.rows["platform_status"]}), 50, 80, 1.0)
        account_id = re.search(r"account_id: (A\d{4})", user).group(1)
        bundle = {
            "account": next(a for a in self.seeded.rows["accounts"] if a["account_id"] == account_id),
            "usage": [u for u in self.seeded.rows["usage"] if u["account_id"] == account_id],
            "invoices": [i for i in self.seeded.rows["invoices"] if i["account_id"] == account_id],
        }
        fault = "wrong_status" if self.always_wrong else (self.faults.pop(0) if self.faults else None)
        if fault == "not_json":
            return LLMReply("Sure! Here is the data: {", 40, 10, 1.0)
        if fault == "wrong_status":
            bundle = json.loads(json.dumps(bundle))
            bundle["account"]["status"] = "active" if bundle["account"]["status"] != "active" else "cancelled"
        if fault == "bad_email":
            bundle = json.loads(json.dumps(bundle))
            bundle["account"]["owner_email"] = "real.person@gmail.com"
        return LLMReply(json.dumps(bundle), 100, 200, 1.0)


def _llm_kwargs(reference_data):
    plan_limits, rules = reference_data
    return dict(seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE, plan_limits=plan_limits, policy_rules=rules, prompts_dir=PROMPTS_DIR)


def test_llm_happy_path_uses_schema_and_records_usage(seeded_data, reference_data) -> None:
    llm = FakeLLM(seeded_data)
    generated, summary = generate_with_llm(llm, **_llm_kwargs(reference_data))
    assert generated.rows["accounts"] == seeded_data.rows["accounts"]
    assert summary.calls == 37 and summary.accepted_first_try == 37 and not summary.fell_back_to_seeded
    assert summary.prompt_tokens > 0 and generated.provenance["model"] == "fake-llm:1"


def test_llm_prompt_marks_invariants_fixed(seeded_data, reference_data) -> None:
    llm = FakeLLM(seeded_data)
    generate_with_llm(llm, **_llm_kwargs(reference_data))
    first_user = llm.calls[0][1]["content"]
    assert "account_id: A1001 (FIXED)" in first_user and "@example.com" in llm.calls[0][0]["content"]
    assert "INV-J" not in first_user and "A9" not in re.findall(r"A\d", first_user)


def test_llm_retries_with_feedback_then_accepts(seeded_data, reference_data) -> None:
    llm = FakeLLM(seeded_data, faults=["not_json", "wrong_status", "bad_email"])
    _, summary = generate_with_llm(llm, **_llm_kwargs(reference_data), max_attempts=4)
    outcomes = [(a.target, a.attempt, a.outcome) for a in summary.attempts if a.target == "A1001"]
    assert outcomes == [("A1001", 1, "invalid_json"), ("A1001", 2, "conformance_error"), ("A1001", 3, "schema_error"), ("A1001", 4, "accepted")]
    feedback = llm.calls[1][-1]["content"]
    assert "previous output had these problems" in feedback
    assert summary.accepted_after_retry == 1


def test_llm_persistent_failure_falls_back_or_fails(seeded_data, reference_data) -> None:
    generated, summary = generate_with_llm(FakeLLM(seeded_data, always_wrong=True), **_llm_kwargs(reference_data), max_attempts=2)
    assert len(summary.fell_back_to_seeded) == 36  # every account; platform_status was accepted
    assert generated.rows["accounts"]  # dataset still complete and validated downstream
    with pytest.raises(LLMGenerationError):
        generate_with_llm(FakeLLM(seeded_data, always_wrong=True), **_llm_kwargs(reference_data), max_attempts=1, fallback="fail")


def test_llm_pipeline_report_includes_llm_section(tmp_path, seeded_data) -> None:
    result = run_pipeline(out_dir=tmp_path, generator="llm", llm=FakeLLM(seeded_data, faults=["wrong_status"]),
                          seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE, account_count=36)
    assert result.ok
    report = (tmp_path / "validation_report.md").read_text(encoding="utf-8")
    assert "## LLM generation" in report and "conformance_error" in report


def test_account_bundle_schema_is_sent_to_the_model() -> None:
    schema = AccountBundle.model_json_schema()
    assert set(schema["properties"]) == {"account", "usage", "invoices"}
