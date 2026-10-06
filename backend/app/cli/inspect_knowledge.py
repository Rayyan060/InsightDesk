"""Inspect the knowledge base.

    python scripts/inspect_knowledge.py                                  # counts by type, category and label
    python scripts/inspect_knowledge.py --source KB-ADV-007              # one document with metadata
    python scripts/inspect_knowledge.py --version 3.9 --as-of 2026-10-06 # which sources apply, and why not
    python scripts/inspect_knowledge.py --export-jsonl out/sections.jsonl  # retrieval-ready section records
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date

from app.cli.common import out, parse_date, project_path, setup_logging
from app.knowledge.catalog import REFERENCE_DATE
from app.knowledge.documents import LABELS_PATH, load_knowledge_base, section_records
from app.knowledge.precedence import AUTHORITY_LABELS, applicability, superseded_by_map
from app.knowledge.validation import read_labels


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="inspect_knowledge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source")
    p.add_argument("--version", help="customer product version, e.g. 3.9")
    p.add_argument("--as-of", type=parse_date, default=date.fromisoformat(REFERENCE_DATE))
    p.add_argument("--export-jsonl", type=project_path)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    setup_logging(args.verbose)

    kb = load_knowledge_base()
    labels = read_labels(LABELS_PATH)
    superseded = superseded_by_map(kb.entries)
    entries_by_id = {e.source_id: e for e in kb.entries}

    if args.export_jsonl:
        args.export_jsonl.parent.mkdir(parents=True, exist_ok=True)
        records = [r for d in sorted(kb.documents.values(), key=lambda d: d.source_id) for r in section_records(d, superseded)]
        with args.export_jsonl.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        out(f"Exported {len(records)} section records to {args.export_jsonl}")
        return 0

    if args.source:
        doc = kb.documents.get(args.source)
        if doc is None:
            out(f"No source {args.source}")
            return 1
        meta = doc.model_dump(mode="json", exclude={"content", "sections", "ticket"})
        meta["authority"] = AUTHORITY_LABELS[doc.authority_level]
        meta["superseded_by"] = superseded.get(doc.source_id, [])
        meta["labels"] = labels.get(doc.source_id, {}).get("labels", [])
        meta["sections"] = [s.heading for s in doc.sections]
        out(json.dumps(meta, indent=2))
        out("")
        out(doc.content)
        return 0

    if args.version:
        out(f"Applicability for version {args.version} on {args.as_of}:")
        for entry in sorted(kb.entries, key=lambda e: (e.authority_level, e.source_id)):
            result = applicability(entry, as_of=args.as_of, product_version=args.version, entries_by_id=entries_by_id, superseded_by=superseded)
            status = "applies" if result.applicable else "excluded: " + ", ".join(result.reasons)
            notice = f"  ({', '.join(result.notices)})" if result.notices else ""
            out(f"  [{entry.authority_level}] {entry.source_id:<15} {status}{notice}")
        return 0

    out(f"Sources: {len(kb.entries)}")
    out("By doc_type: " + json.dumps(dict(Counter(e.doc_type.value for e in kb.entries))))
    out("By category: " + json.dumps(dict(Counter(row.get("category") for row in labels.values()))))
    out("By label: " + json.dumps(dict(Counter(label for row in labels.values() for label in row["labels"]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
