"""Knowledge CLIs: generate refuses to overwrite, inspect works, export is retrieval-ready."""

from __future__ import annotations

import json

from app.cli import generate_knowledge, inspect_knowledge, validate_knowledge
from app.knowledge.documents import load_knowledge_base


def test_generate_refuses_without_force(capsys) -> None:
    assert generate_knowledge.main([]) == 1
    assert "refusing to overwrite" in capsys.readouterr().out


def test_validate_passes_on_committed_kb(capsys) -> None:
    assert validate_knowledge.main(["--no-report"]) == 0
    assert "PASS: 0 errors, 0 warnings" in capsys.readouterr().out


def test_inspect_source_and_applicability(capsys) -> None:
    assert inspect_knowledge.main(["--source", "KB-API-009"]) == 0
    meta = capsys.readouterr().out
    assert '"superseded_by": [\n    "KB-API-014"\n  ]' in meta
    assert inspect_knowledge.main(["--version", "3.9", "--as-of", "2026-10-06"]) == 0
    out = capsys.readouterr().out
    assert "KB-ADV-003      excluded: deprecated" in out and "KB-API-002      applies  (deprecation_upcoming:2026-12-01)" in out


def test_export_jsonl_one_record_per_section(tmp_path) -> None:
    target = tmp_path / "sections.jsonl"
    assert inspect_knowledge.main(["--export-jsonl", str(target)]) == 0
    records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    kb = load_knowledge_base()
    assert len(records) == sum(len(d.sections) for d in kb.documents.values())
    required = {"chunk_id", "source_id", "doc_type", "section", "text", "authority_level", "product_versions", "last_updated", "superseded_by"}
    assert all(required <= set(r) for r in records)
