"""Generate, validate, export and verify the synthetic customer dataset.

    python scripts/generate_data.py                       # seeded (offline, byte-reproducible)
    python scripts/generate_data.py --generator llm       # Ollama, verbatim prompts in data/synthetic/prompts
    python scripts/generate_data.py --force               # replace existing CSVs in data/synthetic

Never writes to the application database: the import check uses a
throwaway SQLite file. Load the result with scripts/load_accounts.py.
"""

from __future__ import annotations

import argparse

from app.cli.common import out, parse_date, project_path, setup_logging
from app.core.config import load_settings
from app.synthetic.pipeline import REFERENCE_DIR, SYNTHETIC_DIR, run_pipeline
from app.synthetic.scenarios import DEFAULT_ACCOUNT_COUNT, DEFAULT_REFERENCE_DATE, DEFAULT_SEED


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="generate_data", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--generator", choices=["seeded", "llm"], default="seeded")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--reference-date", type=parse_date, default=DEFAULT_REFERENCE_DATE)
    p.add_argument("--accounts", type=int, default=DEFAULT_ACCOUNT_COUNT)
    p.add_argument("--out", type=project_path, default=SYNTHETIC_DIR)
    p.add_argument("--reference-dir", type=project_path, default=REFERENCE_DIR)
    p.add_argument("--force", action="store_true", help="overwrite existing CSVs in --out")
    p.add_argument("--ollama-url", default=None, help="default: OLLAMA_BASE_URL")
    p.add_argument("--model", default=None, help="default: OLLAMA_MODEL")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--llm-fallback", choices=["seeded", "fail"], default="seeded",
                   help="when an account's LLM output fails validation after all attempts")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    llm = None
    llm_options = None
    if args.generator == "llm":
        from app.synthetic.llm_generator import OllamaJsonLLM

        settings = load_settings()
        url = args.ollama_url or settings.ollama_base_url
        if not url:
            out("error: no Ollama URL (set OLLAMA_BASE_URL or pass --ollama-url)")
            return 2
        llm = OllamaJsonLLM(url, args.model or settings.ollama_model, timeout_seconds=settings.ollama_timeout_seconds)
        llm_options = {"temperature": args.temperature, "max_attempts": args.max_attempts, "fallback": args.llm_fallback}
    try:
        result = run_pipeline(
            out_dir=args.out,
            reference_dir=args.reference_dir,
            generator=args.generator,
            seed=args.seed,
            reference_date=args.reference_date,
            account_count=args.accounts,
            force=args.force,
            llm=llm,
            llm_options=llm_options,
        )
    finally:
        if llm is not None:
            llm.close()

    for step in result.steps:
        out(f"[{'ok' if step.ok else 'FAILED':>6}] {step.name}: {step.detail}")
    errors = [i for i in result.issues if i.severity == "error"]
    for issue in errors[:30]:
        out(f"  ERROR {issue.table} [{issue.key or issue.row or ''}] {issue.column or ''}: {issue.message}")
    if result.llm_summary:
        s = result.llm_summary
        out(f"LLM: {s['calls']} calls, {s['prompt_tokens']}+{s['completion_tokens']} tokens, fell back: {s['fell_back_to_seeded'] or 'none'}")
    out("PASS" if result.ok else "FAIL")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
