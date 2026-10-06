"""Mutation tests for the provenance-aware reproducibility checks (``provenance_checks.py``).

Each test copies the committed data to a temp directory, applies ONE change and
asserts that the same checks the real-data tests run reject it. The exceptions
are changes that are legitimately equivalent (thousands separators) and the
documented residual limit (free-text LLM fields). Every edit asserts that it
actually changed the file, so no test can pass vacuously.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest
from provenance_checks import verify_knowledge_base, verify_synthetic

from app.knowledge.documents import DATA_DIR
from app.synthetic.pipeline import SYNTHETIC_DIR


def replace_once(path: Path, old: str, new: str, count: int = 1) -> None:
    data = path.read_bytes().decode("utf-8")
    assert data.count(old) == count, f"mutation target {old!r} found {data.count(old)} times in {path.name}"
    path.write_bytes(data.replace(old, new).encode("utf-8"))


# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #
@pytest.fixture
def kb(tmp_path) -> Path:
    root = tmp_path / "data"
    for sub in ("reference", "source_register", "knowledge_base", "tickets"):
        shutil.copytree(DATA_DIR / sub, root / sub)
    verify_knowledge_base(root)  # the unmodified copy passes
    return root


def rejects(root: Path) -> None:
    with pytest.raises(AssertionError):
        verify_knowledge_base(root)


def policies(root: Path, sid: str) -> Path:
    return root / "knowledge_base" / "policies" / f"{sid}.md"


def edit_register(root: Path, sid: str, column: str, value: str) -> None:
    path = root / "source_register" / "source_register.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    target = next(r for r in rows if r["source_id"] == sid)
    assert target[column] != value
    target[column] = value
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_changed_numeric_fact_1499_to_1500_fails(kb) -> None:
    replace_once(policies(kb, "KB-POL-002"), "| priority | 1499 |", "| priority | 1500 |")
    rejects(kb)


def test_thousands_separator_1499_vs_1_499_is_equivalent(kb) -> None:
    replace_once(policies(kb, "KB-POL-002"), "| priority | 1499 |", "| priority | 1,499 |")
    verify_knowledge_base(kb)  # same value, different formatting: accepted


def test_swapping_values_between_table_rows_fails(kb) -> None:
    path = policies(kb, "KB-POL-001")
    replace_once(path, "| Pro | 14 days |", "| Pro | 30 days |")
    replace_once(path, "| Enterprise | 30 days |", "| Enterprise | 14 days |")
    rejects(kb)  # every number is still present in the section; only row binding catches this


def test_swapping_values_in_a_table_rewritten_as_a_list_fails(kb) -> None:
    path = kb / "knowledge_base" / "articles" / "KB-ADV-008.md"
    replace_once(path, "**Pro**: 30 days", "**Pro**: 90 days")
    replace_once(path, "**Business**: 90 days", "**Business**: 30 days")
    rejects(kb)


def test_dropped_fact_fails(kb) -> None:
    replace_once(policies(kb, "KB-POL-002"), "**0.8** (80%)", "most")
    rejects(kb)


def test_invented_fact_fails(kb) -> None:
    replace_once(policies(kb, "KB-POL-001"), "goes to the billing queue.", "goes to the billing queue (error CF-777).")
    rejects(kb)


def test_changed_heading_fails(kb) -> None:
    replace_once(policies(kb, "KB-POL-001"), "## Eligibility", "## Who is eligible")
    rejects(kb)


def test_changed_title_fails(kb) -> None:
    replace_once(policies(kb, "KB-POL-001"), "# Refund policy", "# Refunds")
    rejects(kb)


def test_changed_metadata_fails(kb) -> None:
    edit_register(kb, "KB-POL-001", "last_updated", "2026-09-16")
    rejects(kb)


def test_seeded_fallback_file_must_be_byte_identical(kb) -> None:
    replace_once(policies(kb, "KB-POL-003"), "at least 0.75", "at least  0.75")  # one extra space
    rejects(kb)


def test_injection_fixture_must_be_byte_identical(kb) -> None:
    replace_once(kb / "knowledge_base" / "community" / "COM-0001.md", "Fixed instantly.", "Fixed instantly!")
    rejects(kb)


def test_line_ending_change_in_seeded_file_fails(kb) -> None:
    path = policies(kb, "KB-POL-003")
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    rejects(kb)


def test_line_ending_change_in_llm_file_fails(kb) -> None:
    path = policies(kb, "KB-POL-001")
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    rejects(kb)


def test_relabelling_seeded_source_as_llm_fails(kb) -> None:
    edit_register(kb, "KB-POL-003", "provenance", "LLM: qwen2.5:7b, prompt v1")
    rejects(kb)


def test_manifest_must_list_every_rewritten_source(kb) -> None:
    path = kb / "source_register" / "kb_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["llm"]["rewritten"].remove("KB-POL-001")
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    rejects(kb)


def test_extra_file_on_disk_fails(kb) -> None:
    (kb / "knowledge_base" / "articles" / "KB-GS-999.md").write_text("# Stray\n\n## Body\n\ntext\n", encoding="utf-8")
    rejects(kb)


def test_llm_ticket_non_prose_field_change_fails(kb) -> None:
    log = json.loads((kb / "source_register" / "kb_llm_attempts.json").read_text(encoding="utf-8"))
    sid = next(s for s in log["rewritten"] if s.startswith("TKT-"))
    path = kb / "tickets" / f"{sid}.json"
    ticket = json.loads(path.read_text(encoding="utf-8"))
    ticket["escalated_to_human"] = not ticket["escalated_to_human"]
    path.write_text(json.dumps(ticket, indent=2) + "\n", encoding="utf-8")
    rejects(kb)


# --------------------------------------------------------------------------- #
# Synthetic account data
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def scratch(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("provenance_scratch")


@pytest.fixture
def syn(tmp_path, scratch) -> Path:
    target = tmp_path / "synthetic"
    shutil.copytree(SYNTHETIC_DIR, target, ignore=shutil.ignore_patterns("prompts"))
    verify_synthetic(target, scratch)  # the unmodified copy passes
    return target


def syn_rejects(target: Path, scratch: Path) -> None:
    with pytest.raises(AssertionError):
        verify_synthetic(target, scratch)


def account_line(target: Path, account_id: str) -> str:
    return next(line for line in (target / "accounts.csv").read_text(encoding="utf-8").splitlines() if line.startswith(account_id + ","))


def test_fallback_account_must_be_byte_identical(syn, scratch) -> None:
    line = account_line(syn, "A1004")  # A1004 fell back to the seeded filler
    replace_once(syn / "accounts.csv", line, line.replace(",Pro,", ",PRO,"))
    syn_rejects(syn, scratch)  # parses to the same model ('PRO' -> 'Pro'), but the bytes differ


def test_fallback_usage_value_change_fails(syn, scratch) -> None:
    lines = (syn / "usage.csv").read_text(encoding="utf-8").splitlines()
    line = next(item for item in lines if item.startswith("A1004,2026-08,"))
    fields = line.split(",")
    fields[2] = str(int(fields[2]) + 1)
    replace_once(syn / "usage.csv", line, ",".join(fields))
    syn_rejects(syn, scratch)


def test_llm_account_pinned_boundary_value_fails(syn, scratch) -> None:
    # A1003 (LLM-filled) carries "workflow runs exactly at the Pro limit": 20000.
    lines = (syn / "usage.csv").read_text(encoding="utf-8").splitlines()
    line = next(item for item in lines if item.startswith("A1003,2026-10,"))
    assert line.split(",")[2] == "20000"
    replace_once(syn / "usage.csv", line, line.replace(",20000,", ",19999,"))
    syn_rejects(syn, scratch)


def test_llm_free_text_field_is_schema_protected_only(syn, scratch) -> None:
    """Documented residual limit: an LLM run cannot be replayed, so its free-text values
    (company name, email) are protected by schema validation only, not byte equality."""
    line = account_line(syn, "A1001")
    replace_once(syn / "accounts.csv", line, line.replace("TechSolve Inc", "TechSolve Ltd"))
    verify_synthetic(syn, scratch)
    replace_once(syn / "accounts.csv", "TechSolve Ltd", "TechSolve Ltd,extra")  # but structure is still enforced
    syn_rejects(syn, scratch)


def test_manifest_fallback_list_must_match_data(syn, scratch) -> None:
    path = syn / "generation_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["llm"]["fell_back_to_seeded"].append("A1001")  # A1001 was LLM-filled
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    syn_rejects(syn, scratch)


def test_line_endings_change_fails(syn, scratch) -> None:
    path = syn / "invoices.csv"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    syn_rejects(syn, scratch)


def test_edge_case_manifest_must_be_byte_identical(syn, scratch) -> None:
    replace_once(syn / "edge_cases.csv", "A1003,", "A1033,")
    syn_rejects(syn, scratch)


def test_extra_row_fails(syn, scratch) -> None:
    path = syn / "usage.csv"
    path.write_bytes(path.read_bytes() + b"A1001,2026-07,10,10,1\n")
    syn_rejects(syn, scratch)
