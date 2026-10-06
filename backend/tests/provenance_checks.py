"""Provenance-aware reproducibility checks for the committed datasets.

Shared by the real-data tests and the mutation tests (``test_provenance_hardening.py``),
so both exercise exactly the same logic. Each function raises ``AssertionError``
on the first violation.

A committed artifact is either:

* **seeded**: produced by the deterministic generators, so it must be
  **byte-identical** to a fresh render with the recorded seed; or
* **LLM**: produced by a real Ollama run, which cannot be replayed byte-for-byte.
  It must then agree with the run's recorded provenance (manifest and attempt
  log), and must keep every invariant the generator enforced: metadata, titles,
  headings, every fact bound to its table row, and every pinned account value.
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
from pathlib import Path

# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #
_TABLE_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")


def row_binding_problems(want_section: str, got_section: str, *, scope: str) -> list[str]:
    """Each spec table row with facts must survive as ONE line (table row or list item)
    naming its key and containing all of its facts as whole tokens.

    Format-independent (an LLM may turn a table into a list), but value-exact:
    swapping values between rows, or changing a value, fails. Numbers are
    compared without thousands separators (1,499 == 1499; 1499 != 1500).
    """
    from app.knowledge.generator import _normalise_numbers, extract_facts

    lines = [_normalise_numbers(line) for line in got_section.splitlines() if line.strip()]
    problems = []
    for key, row in table_rows(want_section).items():
        facts = extract_facts(_normalise_numbers(row))
        if not facts:
            continue  # header rows carry no facts
        bound = any(key in re.sub(r"[*`]", "", line).lower() and facts <= extract_facts(line) for line in lines)
        if not bound:
            problems.append(f"{scope}: row '{key}' facts {sorted(facts)} are not together on one line")
    return problems


def table_rows(text: str) -> dict[str, str]:
    """Markdown table rows keyed by their first cell (lower-cased, without ** or `)."""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or _TABLE_SEPARATOR.fullmatch(stripped):
            continue
        first = stripped.strip("|").split("|")[0]
        rows.setdefault(re.sub(r"[*`]", "", first).strip().lower(), stripped)
    return rows


def verify_knowledge_base(data_dir: Path) -> None:
    from app.knowledge.documents import DOC_DIRS, DATA_DIR, load_knowledge_base, parse_markdown
    from app.knowledge.generator import MANIFEST_NAME, SEEDED_PROVENANCE, fact_problems, generate_seeded
    from app.knowledge.catalog import REFERENCE_DATE, SPEC_VERSION
    from app.schemas.ingestion import SOURCE_REGISTER_COLUMNS

    register_dir = data_dir / "source_register"
    manifest = json.loads((register_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert (manifest["reference_date"], manifest["spec_version"]) == (REFERENCE_DATE, SPEC_VERSION)
    expected = generate_seeded(manifest["seed"])

    kb = load_knowledge_base(data_dir)
    assert [i for i in kb.issues if i.severity == "error"] == [], [vars(i) for i in kb.issues]

    # Same corpus: exactly the generator's files on disk, nothing extra.
    on_disk = set()
    for directory in DOC_DIRS.values():
        target = data_dir / directory.relative_to(DATA_DIR)
        on_disk |= {p.relative_to(data_dir).as_posix() for p in target.glob("*.md")} | {
            p.relative_to(data_dir).as_posix() for p in target.glob("TKT-*.json")}
    assert on_disk == set(expected.files), sorted(on_disk ^ set(expected.files))

    # Metadata: everything except provenance equals the generator's register.
    metadata = set(SOURCE_REGISTER_COLUMNS) - {"provenance"}
    expected_entries = {e.source_id: e for e in expected.register}
    assert set(kb.documents) == set(expected_entries)
    for sid, entry in expected_entries.items():
        assert kb.documents[sid].model_dump(include=metadata) == entry.model_dump(include=metadata), sid

    # Provenance partition must agree with the run's manifest and attempt log.
    all_ids = set(expected_entries)
    if manifest["generator"] == "seeded":
        rewritten, seeded_ids = set(), all_ids
        assert manifest["provenance"] == SEEDED_PROVENANCE
    else:
        assert manifest["generator"] == "llm"
        log = json.loads((register_dir / "kb_llm_attempts.json").read_text(encoding="utf-8"))
        llm = manifest["llm"]
        assert manifest["provenance"] == f"LLM: {llm['model']}, prompt {llm['prompt_version']}"
        assert (log["model"], log["seed"], log["calls"]) == (llm["model"], llm["seed"], llm["calls"])
        assert log["calls"] == len(log["attempts"])
        rewritten, fell_back, fixtures = set(log["rewritten"]), set(log["fell_back_to_seeded"]), set(log["verbatim_fixtures"])
        # Manifest and attempt log must list exactly the same sources.
        assert (set(llm["rewritten"]), set(llm["fell_back_to_seeded"]), set(llm["verbatim_fixtures"])) == (rewritten, fell_back, fixtures)
        assert not (rewritten & fell_back or rewritten & fixtures or fell_back & fixtures)
        assert rewritten | fell_back | fixtures == all_ids
        outcomes: dict[str, list[str]] = {}
        for attempt in log["attempts"]:
            outcomes.setdefault(attempt["source_id"], []).append(attempt["outcome"])
        for sid in rewritten:
            assert outcomes.get(sid, [])[-1:] == ["accepted"], sid
        for sid in fell_back:
            assert "accepted" not in outcomes.get(sid, []), sid
        assert not set(outcomes) & fixtures  # fixtures are never sent to the model
        seeded_ids = fell_back | fixtures

    prose_fields = ("customer_question", "resolution")
    for rel, content in expected.files.items():
        sid = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        committed_bytes = (data_dir / rel).read_bytes()
        provenance = kb.documents[sid].provenance
        if sid in seeded_ids:
            assert provenance == SEEDED_PROVENANCE, sid
            assert committed_bytes == content.encode("utf-8"), f"{rel} is not byte-identical to the seeded render"
            continue

        assert provenance == manifest["provenance"] and sid in rewritten, sid
        committed = committed_bytes.decode("utf-8")
        assert "\r" not in committed, f"{rel}: line endings changed"
        if rel.startswith("tickets/"):
            want, got = json.loads(content), json.loads(committed)
            assert {k: v for k, v in got.items() if k not in prose_fields} == {k: v for k, v in want.items() if k not in prose_fields}, sid
            for field in prose_fields:
                assert fact_problems(want[field], got[field], scope=f"{sid}.{field}") == []
            continue

        want_title, want_sections = parse_markdown(content)
        got_title, got_sections = parse_markdown(committed)
        assert got_title == want_title, sid
        assert [s.heading for s in got_sections] == [s.heading for s in want_sections], sid
        for want_section, got_section in zip(want_sections, got_sections):
            scope = f"{sid}/{want_section.heading}"
            assert fact_problems(want_section.text, got_section.text, scope=scope) == []
            # Facts stay bound to their table row (no swapping values between rows).
            assert row_binding_problems(want_section.text, got_section.text, scope=scope) == []


# --------------------------------------------------------------------------- #
# Synthetic account data
# --------------------------------------------------------------------------- #
TABLE_KEYS = {"accounts": 0, "usage": 0, "invoices": 1}  # index of account_id in each CSV


def _lines_by_account(path: Path, table: str) -> tuple[str, dict[str, list[str]]]:
    text = path.read_bytes().decode("utf-8")
    assert "\r" not in text, f"{path.name}: line endings changed"
    header, *lines = text.split("\n")
    grouped: dict[str, list[str]] = {}
    for line in lines:
        if line:
            account_id = next(csv.reader(io.StringIO(line)))[TABLE_KEYS[table]]
            grouped.setdefault(account_id, []).append(line)
    return header, grouped


def verify_synthetic(synthetic_dir: Path, scratch: Path) -> None:
    from app.database.csv_io import parse_rows, read_csv, write_table_csv
    from app.database.row_schemas import ROW_MODELS
    from app.synthetic.generator import build_blueprints, check_conformance, fill_seeded, platform_status_rows
    from app.synthetic.pipeline import PROVENANCE_JSON, load_reference, run_pipeline
    from app.synthetic.scenarios import DEFAULT_REFERENCE_DATE, DEFAULT_SEED

    manifest = json.loads((synthetic_dir / PROVENANCE_JSON).read_text(encoding="utf-8"))
    provenance = manifest["provenance"]
    assert (provenance["seed"], provenance["reference_date"], provenance["account_count"]) == (
        DEFAULT_SEED, DEFAULT_REFERENCE_DATE.isoformat(), 36)

    fresh = scratch / "fresh"
    if not (fresh / "edge_cases.csv").exists():
        assert run_pipeline(out_dir=fresh, seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE, account_count=36).ok
    tables = ("accounts", "usage", "invoices", "platform_status")

    if provenance["generator"] == "seeded":
        for name in (*[f"{t}.csv" for t in tables], "edge_cases.csv"):
            assert (fresh / name).read_bytes() == (synthetic_dir / name).read_bytes(), name
        return

    assert provenance["generator"] == "llm" and provenance["model"]
    llm = manifest["llm"]
    assert (llm["model"], llm["seed"], llm["calls"]) == (provenance["model"], DEFAULT_SEED, len(llm["attempts"]))
    # Deterministic artifacts stay byte-identical, including every CSV header.
    assert (fresh / "edge_cases.csv").read_bytes() == (synthetic_dir / "edge_cases.csv").read_bytes()
    for table in tables:
        assert (synthetic_dir / f"{table}.csv").read_bytes().split(b"\n", 1)[0] == (fresh / f"{table}.csv").read_bytes().split(b"\n", 1)[0], table

    committed: dict[str, list[dict]] = {}
    for table in tables:
        raw, read_issues = read_csv(synthetic_dir / f"{table}.csv", table)
        parsed, parse_issues = parse_rows(table, raw)
        assert not read_issues and not parse_issues, (table, [i.to_dict() for i in read_issues + parse_issues])
        committed[table] = [row.model_dump() for _, row in parsed]
    assert {t: len(rows) for t, rows in committed.items()} == {t: manifest["counts"][t] for t in tables}

    plan_limits, rules, _ = load_reference()
    blueprints, rng = build_blueprints(seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE,
                                       plan_limits=plan_limits, policy_rules=rules, account_count=36)
    assert sorted(a["account_id"] for a in committed["accounts"]) == [bp.account_id for bp in blueprints]

    # Attempt log and manifest agree on who was LLM-filled and who fell back.
    fell_back = set(llm["fell_back_to_seeded"])
    accepted = {a["target"] for a in llm["attempts"] if a["outcome"] == "accepted"}
    targets = {bp.account_id for bp in blueprints} | {"platform_status"}
    assert not accepted & fell_back and accepted | fell_back == targets, sorted(targets - accepted - fell_back)
    assert len(accepted) == llm["accepted_first_try"] + llm["accepted_after_retry"]

    committed_lines = {table: _lines_by_account(synthetic_dir / f"{table}.csv", table)[1] for table in TABLE_KEYS}
    sort_keys = {"accounts": "account_id", "usage": "period", "invoices": "invoice_id"}
    for index, bp in enumerate(blueprints):
        if bp.account_id in fell_back:
            # Byte-for-byte: render the deterministic fallback exactly as the exporter does.
            raw = fill_seeded([bp], random.Random(DEFAULT_SEED + index))
            for table in TABLE_KEYS:
                path = scratch / f"fallback_{bp.account_id}_{table}.csv"
                write_table_csv(path, table, [ROW_MODELS[table].model_validate(r) for r in raw[table]], overwrite=True)
                expected_lines = [line for line in path.read_bytes().decode("utf-8").split("\n")[1:] if line]
                assert committed_lines[table].get(bp.account_id, []) == expected_lines, f"{bp.account_id} {table}: fallback rows not byte-identical"
        else:
            rows = {t: sorted((r for r in committed[t] if r["account_id"] == bp.account_id), key=lambda r: r[k]) for t, k in sort_keys.items()}
            bundle = {"account": rows["accounts"][0], "usage": rows["usage"], "invoices": rows["invoices"]}
            assert check_conformance(bp, bundle) == [], (bp.account_id, check_conformance(bp, bundle))

    fixed = [ROW_MODELS["platform_status"].model_validate(r).model_dump() for r in platform_status_rows(DEFAULT_REFERENCE_DATE, rng)]
    by_component = lambda rows: sorted(rows, key=lambda r: r["component"])  # noqa: E731
    if "platform_status" in fell_back:
        assert by_component(committed["platform_status"]) == by_component(fixed)
    else:
        invariant = lambda rows: [(r["component"], r["status"], r["incident_id"]) for r in by_component(rows)]  # noqa: E731
        assert invariant(committed["platform_status"]) == invariant(fixed)
