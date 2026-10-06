"""Generate the CloudFlow knowledge base, Source Register and labels, then validate.

    python scripts/generate_knowledge.py --force                      # seeded (default), reproducible
    python scripts/generate_knowledge.py --generator llm --force      # Ollama rewrite with fact checks

Refuses to overwrite an existing knowledge base without ``--force``.
Validation runs afterwards; a failing validation exits 1.
"""

from __future__ import annotations

import argparse
import json

from app.cli.common import out, setup_logging
from app.cli.validate_knowledge import run_validation
from app.core.config import load_settings
from app.knowledge.documents import REGISTER_DIR
from app.knowledge.generator import DEFAULT_SEED, generate_seeded, generate_with_llm, reference_date, write_knowledge


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="generate_knowledge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--generator", choices=["seeded", "llm"], default="seeded")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--force", action="store_true", help="replace the existing knowledge base")
    p.add_argument("--ollama-url", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--llm-fallback", choices=["seeded", "fail"], default="seeded")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    setup_logging(args.verbose)

    if (REGISTER_DIR / "source_register.csv").exists() and not args.force:
        out("refusing to overwrite the existing knowledge base (use --force)")
        return 1

    if args.generator == "seeded":
        generated = generate_seeded(args.seed)
    else:
        from app.synthetic.llm_generator import OllamaJsonLLM

        settings = load_settings()
        url = args.ollama_url or settings.ollama_base_url
        if not url:
            out("error: no Ollama URL (set OLLAMA_BASE_URL or pass --ollama-url)")
            return 2
        llm = OllamaJsonLLM(url, args.model or settings.ollama_model, timeout_seconds=settings.ollama_timeout_seconds)
        try:
            generated, summary = generate_with_llm(llm, seed=args.seed, temperature=args.temperature,
                                                   max_attempts=args.max_attempts, fallback=args.llm_fallback)
        finally:
            llm.close()
        (REGISTER_DIR / "kb_llm_attempts.json").parent.mkdir(parents=True, exist_ok=True)
        (REGISTER_DIR / "kb_llm_attempts.json").write_text(json.dumps(summary.to_dict(), indent=2) + "\n", encoding="utf-8")
        out(f"LLM: {summary.calls} calls, rewritten {len(summary.rewritten)}, fell back {len(summary.fell_back_to_seeded)}")

    written = write_knowledge(generated, force=args.force)
    out(f"Wrote {len(written)} documents and {len(generated.register)} source-register entries")
    return run_validation(reference_date(), write_report=True)


if __name__ == "__main__":
    raise SystemExit(main())
