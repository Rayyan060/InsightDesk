"""Knowledge-base generation: specs → Markdown/JSON documents + Source Register.

``seeded`` (default) renders the specs deterministically; the seed picks each
ticket's customer phrasing. Same seed, same bytes.

``llm`` asks Ollama (``JsonLLM``) to rewrite each section's prose. Output is
accepted only if:

* it matches the JSON schema;
* headings are identical and in order;
* every fact in the spec is still present (error codes, versions, numbers, KB
  IDs, ``code``, **UI labels**);
* no new error codes, versions, document IDs or URLs were introduced;
* no assistant-addressed instructions appear.

Failed documents are retried with the problems fed back, then fall back to the
seeded render (recorded). Adversarial fixtures (``llm_rewrite=False``) are
always rendered verbatim.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from string import Template
from typing import Any, Literal

from pydantic import BaseModel

from app.knowledge.catalog import REFERENCE_DATE, SPEC_VERSION, DocSpec, TicketSpec, all_doc_specs, all_ticket_specs
from app.knowledge.documents import (
    DATA_DIR,
    DOC_DIRS,
    LABELS_PATH,
    REGISTER_DIR,
    TicketRecord,
    document_path,
    render_markdown,
    write_register,
)
from app.knowledge.safety import scan_for_instructions
from app.schemas.ingestion import AUTHORITY_BY_DOC_TYPE, DocType, SourceRegisterEntry

DEFAULT_SEED = 20261006
PROMPT_VERSION = "v1"
PROMPTS_DIR = DATA_DIR / "synthetic" / "prompts"
MANIFEST_NAME = "kb_manifest.json"
SEEDED_PROVENANCE = f"Spec-authored with an AI coding assistant; seeded render (spec {SPEC_VERSION})"


@dataclass
class GeneratedKnowledge:
    files: dict[str, str]  # path relative to data/ -> content
    register: list[SourceRegisterEntry]
    labels: list[dict[str, str]]
    manifest: dict[str, Any]


# ---------------------------------------------------------------------- #
# Facts (for LLM conformance)
# ---------------------------------------------------------------------- #
_FACT_PATTERNS = (
    re.compile(r"\bCF-\d{3}\b"),
    re.compile(r"\b(?:KB-[A-Z]+-\d{3}|RN-\d{4}-\d{2}|TKT-\d{4}-\d{4}|INV-[A-Z0-9-]+|A\d{4})\b"),
    re.compile(r"`[^`]+`"),
    re.compile(r"\*\*[^*]+\*\*"),
    re.compile(r"\b\d+\.\d+\+?(?:\.\d+)?\b"),
    re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d+\b"),
)
_NEW_FACT_PATTERNS = (
    re.compile(r"\bCF-\d{3}\b"),
    re.compile(r"\b(?:KB-[A-Z]+-\d{3}|RN-\d{4}-\d{2}|TKT-\d{4}-\d{4})\b"),
    re.compile(r"\b\d+\.\d\b(?!\d)"),
    re.compile(r"https?://\S+"),
)


def extract_facts(text: str) -> set[str]:
    facts: set[str] = set()
    for pattern in _FACT_PATTERNS:
        facts.update(m.group(0) for m in pattern.finditer(text))
    return facts


_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _normalise_numbers(text: str) -> str:
    """'1,499' and '1499' state the same fact; compare numbers without thousands separators."""
    return _THOUSANDS_SEPARATOR.sub("", text)


def fact_problems(spec_text: str, generated: str, *, scope: str) -> list[str]:
    spec_text, generated = _normalise_numbers(spec_text), _normalise_numbers(generated)
    problems = [f"{scope}: missing fact {fact}" for fact in sorted(extract_facts(spec_text)) if fact not in generated]
    allowed = set()
    for pattern in _NEW_FACT_PATTERNS:
        allowed.update(m.group(0) for m in pattern.finditer(spec_text))
    for pattern in _NEW_FACT_PATTERNS:
        for match in pattern.finditer(generated):
            if match.group(0) not in allowed:
                problems.append(f"{scope}: introduced a fact not in the source: {match.group(0)}")
    if scan_for_instructions(generated) and not scan_for_instructions(spec_text):
        problems.append(f"{scope}: contains text addressed to an assistant")
    return problems


# ---------------------------------------------------------------------- #
# Rendering
# ---------------------------------------------------------------------- #
def _entry(spec: DocSpec | TicketSpec, doc_type: DocType, title: str, provenance: str) -> SourceRegisterEntry:
    if isinstance(spec, TicketSpec):
        return SourceRegisterEntry(
            source_id=spec.id, doc_type=doc_type, title=title, authority_level=AUTHORITY_BY_DOC_TYPE[doc_type],
            product_versions=spec.product_versions, last_updated=spec.resolved_at, effective_from=None,
            deprecated_on=spec.deprecated_on, supersedes=[], provenance=provenance, synthetic=True,
        )
    return SourceRegisterEntry(
        source_id=spec.source_id, doc_type=doc_type, title=title, authority_level=AUTHORITY_BY_DOC_TYPE[doc_type],
        product_versions=spec.product_versions, last_updated=spec.last_updated, effective_from=spec.effective_from,
        deprecated_on=spec.deprecated_on, supersedes=list(spec.supersedes), provenance=provenance, synthetic=True,
    )


def _ticket_record(spec: TicketSpec, question: str, resolution: str) -> TicketRecord:
    return TicketRecord(
        id=spec.id, subject=spec.subject, customer_question=question, intent=spec.intent, resolution=resolution,
        tags=list(spec.tags), resolved_at=spec.resolved_at, product_version=spec.product_version,
        escalated_to_human=spec.escalated_to_human,
    )


def _ticket_json(record: TicketRecord) -> str:
    return json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def _label_row(spec: DocSpec | TicketSpec) -> dict[str, str]:
    is_ticket = isinstance(spec, TicketSpec)
    return {
        "source_id": spec.id if is_ticket else spec.source_id,
        "doc_type": "ticket" if is_ticket else spec.doc_type,
        "category": "ticket" if is_ticket else spec.category,
        "labels": ";".join(spec.labels),
        "conflicts_with": ";".join(spec.conflicts_with),
        "note": spec.note,
    }


def _relpath(path: Path) -> str:
    return path.relative_to(DATA_DIR).as_posix()


def generate_seeded(seed: int = DEFAULT_SEED) -> GeneratedKnowledge:
    rng = random.Random(seed)
    files: dict[str, str] = {}
    register: list[SourceRegisterEntry] = []
    labels: list[dict[str, str]] = []
    for spec in all_doc_specs():
        doc_type = DocType(spec.doc_type)
        files[_relpath(document_path(doc_type, spec.source_id))] = render_markdown(spec.title, list(spec.sections))
        register.append(_entry(spec, doc_type, spec.title, SEEDED_PROVENANCE))
        labels.append(_label_row(spec))
    for spec in all_ticket_specs():
        question = rng.choice(spec.question_variants)
        files[_relpath(document_path(DocType.TICKET, spec.id))] = _ticket_json(_ticket_record(spec, question, spec.resolution))
        register.append(_entry(spec, DocType.TICKET, spec.subject, SEEDED_PROVENANCE))
        labels.append(_label_row(spec))
    manifest = {"generator": "seeded", "seed": seed, "spec_version": SPEC_VERSION, "reference_date": REFERENCE_DATE,
                "provenance": SEEDED_PROVENANCE, "llm": None}
    return GeneratedKnowledge(files, register, labels, manifest)


# ---------------------------------------------------------------------- #
# LLM path
# ---------------------------------------------------------------------- #
class _SectionOut(BaseModel):
    heading: str
    body: str


class DocumentRewrite(BaseModel):
    sections: list[_SectionOut]


class TicketRewrite(BaseModel):
    customer_question: str
    resolution: str


@dataclass
class KBAttempt:
    source_id: str
    attempt: int
    outcome: Literal["accepted", "invalid_json", "schema_error", "conformance_error", "call_failed"]
    problems: list[str] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class KBLLMSummary:
    model: str
    temperature: float
    seed: int
    prompt_version: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    rewritten: list[str] = field(default_factory=list)
    fell_back_to_seeded: list[str] = field(default_factory=list)
    verbatim_fixtures: list[str] = field(default_factory=list)
    attempts: list[KBAttempt] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["attempts"] = [asdict(a) for a in self.attempts]
        return data


def _ask(llm: Any, system: str, user: str, schema_model: type[BaseModel], check, *, source_id: str, seed: int,
         temperature: float, max_attempts: int, summary: KBLLMSummary) -> BaseModel | None:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(1, max_attempts + 1):
        log = KBAttempt(source_id, attempt, "accepted")
        summary.attempts.append(log)
        summary.calls += 1
        try:
            reply = llm.chat_json(messages, schema_model.model_json_schema(), temperature=temperature, seed=seed + attempt)
        except Exception as exc:  # network / HTTP errors
            log.outcome, log.problems = "call_failed", [type(exc).__name__]
            continue
        log.prompt_tokens, log.completion_tokens = reply.prompt_tokens, reply.completion_tokens
        summary.prompt_tokens += reply.prompt_tokens or 0
        summary.completion_tokens += reply.completion_tokens or 0
        try:
            parsed = schema_model.model_validate(json.loads(reply.text))
        except json.JSONDecodeError:
            log.outcome, log.problems = "invalid_json", ["output was not valid JSON"]
        except ValueError as exc:
            log.outcome, log.problems = "schema_error", [str(exc).splitlines()[0]]
        else:
            problems = check(parsed)
            if not problems:
                return parsed
            log.outcome, log.problems = "conformance_error", problems
        messages = messages + [
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": "Your previous output had these problems:\n- " + "\n- ".join(log.problems[:20])
             + "\nReturn the corrected JSON object only."},
        ]
    return None


def generate_with_llm(llm: Any, *, seed: int = DEFAULT_SEED, temperature: float = 0.2, max_attempts: int = 3,
                      fallback: Literal["seeded", "fail"] = "seeded", prompts_dir: Path = PROMPTS_DIR) -> tuple[GeneratedKnowledge, KBLLMSummary]:
    base = generate_seeded(seed)  # fixes ticket phrasing choice and provides fallbacks
    summary = KBLLMSummary(model=llm.model, temperature=temperature, seed=seed, prompt_version=PROMPT_VERSION)
    read = lambda name: (prompts_dir / f"{name}_{PROMPT_VERSION}.md").read_text(encoding="utf-8")  # noqa: E731
    system, doc_template, ticket_template = read("kb_system"), read("kb_document"), read("kb_ticket")
    provenance = f"LLM: {llm.model}, prompt {PROMPT_VERSION}"
    files = dict(base.files)
    entries = {e.source_id: e for e in base.register}

    for index, spec in enumerate(all_doc_specs()):
        if not spec.llm_rewrite:
            summary.verbatim_fixtures.append(spec.source_id)
            continue
        sections_text = "\n\n".join(f"### {h}\n{b}" for h, b in spec.sections)
        user = Template(doc_template).substitute(doc_type=spec.doc_type.replace("_", " "), title=spec.title,
                                                 product_versions=spec.product_versions, last_updated=spec.last_updated,
                                                 sections=sections_text)

        def check(parsed: BaseModel, spec: DocSpec = spec) -> list[str]:
            assert isinstance(parsed, DocumentRewrite)
            got = [s.heading.strip() for s in parsed.sections]
            want = [h for h, _ in spec.sections]
            if got != want:
                return [f"headings must be exactly {want}"]
            problems = []
            for (heading, body), out in zip(spec.sections, parsed.sections):
                problems += fact_problems(body, out.body, scope=heading)
            return problems

        result = _ask(llm, system, user, DocumentRewrite, check, source_id=spec.source_id, seed=seed + index * 10,
                      temperature=temperature, max_attempts=max_attempts, summary=summary)
        if result is None:
            if fallback == "fail":
                raise RuntimeError(f"LLM rewrite of {spec.source_id} failed validation")
            summary.fell_back_to_seeded.append(spec.source_id)
            continue
        assert isinstance(result, DocumentRewrite)
        doc_type = DocType(spec.doc_type)
        files[_relpath(document_path(doc_type, spec.source_id))] = render_markdown(spec.title, [(s.heading, s.body) for s in result.sections])
        entries[spec.source_id] = entries[spec.source_id].model_copy(update={"provenance": provenance})
        summary.rewritten.append(spec.source_id)

    for index, spec in enumerate(all_ticket_specs()):
        if not spec.llm_rewrite:
            summary.verbatim_fixtures.append(spec.id)
            continue
        current = TicketRecord.model_validate(json.loads(files[_relpath(document_path(DocType.TICKET, spec.id))]))
        user = Template(ticket_template).substitute(subject=spec.subject, product_version=spec.product_version, intent=spec.intent,
                                                    customer_question=current.customer_question, resolution=spec.resolution)

        def check_ticket(parsed: BaseModel, current: TicketRecord = current, spec: TicketSpec = spec) -> list[str]:
            assert isinstance(parsed, TicketRewrite)
            return (fact_problems(current.customer_question, parsed.customer_question, scope="customer_question")
                    + fact_problems(spec.resolution, parsed.resolution, scope="resolution"))

        result = _ask(llm, system, user, TicketRewrite, check_ticket, source_id=spec.id, seed=seed + 5000 + index * 10,
                      temperature=temperature, max_attempts=max_attempts, summary=summary)
        if result is None:
            if fallback == "fail":
                raise RuntimeError(f"LLM rewrite of {spec.id} failed validation")
            summary.fell_back_to_seeded.append(spec.id)
            continue
        assert isinstance(result, TicketRewrite)
        files[_relpath(document_path(DocType.TICKET, spec.id))] = _ticket_json(_ticket_record(spec, result.customer_question, result.resolution))
        entries[spec.id] = entries[spec.id].model_copy(update={"provenance": provenance})
        summary.rewritten.append(spec.id)

    manifest = dict(base.manifest, generator="llm", provenance=provenance, llm={k: v for k, v in summary.to_dict().items() if k != "attempts"})
    return GeneratedKnowledge(files, list(entries.values()), base.labels, manifest), summary


# ---------------------------------------------------------------------- #
# Writing
# ---------------------------------------------------------------------- #
def write_knowledge(generated: GeneratedKnowledge, *, data_dir: Path = DATA_DIR, force: bool = False) -> list[Path]:
    register_path = data_dir / "source_register" / "source_register.csv"
    if register_path.exists() and not force:
        raise FileExistsError(f"{register_path} exists; pass force=True (--force) to regenerate the knowledge base")
    # Remove previously generated documents so deleted specs don't linger.
    for doc_type, directory in DOC_DIRS.items():
        target = data_dir / directory.relative_to(DATA_DIR)
        pattern = "TKT-*.json" if doc_type is DocType.TICKET else "*.md"
        if target.exists():
            for old in target.glob(pattern):
                old.unlink()
    written = []
    for rel, content in sorted(generated.files.items()):
        path = data_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    write_register(generated.register, register_path)
    labels_path = data_dir / LABELS_PATH.relative_to(DATA_DIR)
    import csv

    with labels_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_id", "doc_type", "category", "labels", "conflicts_with", "note"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(generated.labels, key=lambda r: r["source_id"]))
    manifest = dict(generated.manifest, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    counts=_counts(generated.register))
    (data_dir / REGISTER_DIR.relative_to(DATA_DIR) / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return written


def _counts(register: list[SourceRegisterEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in register:
        counts[entry.doc_type.value] = counts.get(entry.doc_type.value, 0) + 1
    counts["total"] = len(register)
    return counts


def reference_date() -> date:
    return date.fromisoformat(REFERENCE_DATE)
