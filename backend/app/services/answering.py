"""Grounded answering for ``POST /support`` (minimal demo flow, deterministic).

Pipeline: safety guard → account-scope guard → retrieval → evidence selection
→ extractive answer with citations.

* **Answers come only from retrieved evidence.** The answer is assembled from
  sentences and table rows of retrieved sections, each followed by its
  ``[SOURCE-ID]``. Nothing is generated beyond the evidence. Ollama generation
  isn't wired in (Ollama is unavailable on the build machine); this extractive
  path is the documented fallback.
* **Evidence is authoritative documentation only:** authority 1–2 (articles,
  policies, release notes). Resolved tickets (4) and community posts (5) are
  never used as answer evidence, so outdated tickets and injected text cannot
  shape the answer.
* **Documents are data.** Retrieved text is never executed or obeyed. Messages
  that try to override instructions or reach another account are refused
  before retrieval (R8, R10).
* **No invented account facts.** Account tools are Phase 5, so questions about
  the customer's own records get an insufficient-evidence answer instead of a
  guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.knowledge.safety import scan_for_instructions
from app.rag.embeddings import tokens
from app.rag.retriever import RetrievedChunk, Retriever
from app.schemas.support import AnswerType, Citation, DocType

_ACCOUNT_ID = re.compile(r"\bA\d{4}\b")
_OTHER_ACCOUNT = re.compile(r"\b(another|other|someone else'?s?|different)\s+(customer|account|user|company)", re.I)
_OWN_ACCOUNT = re.compile(
    r"\bmy\s+(account|invoices?|bill(ing)?|plan|usage|subscription|payments?|card|charges?|workspace)\b"
    r"|\b(suspended|charged me|past[_ ]due|why was i)\b",
    re.I,
)
ENTITIES = {"free", "pro", "business", "enterprise"}
MIN_STATEMENT_SCORE = 2


@dataclass
class Answer:
    answer_type: AnswerType
    answer: str
    citations: list[Citation] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    excluded: dict[str, list[str]] = field(default_factory=dict)


def _citation(chunk: RetrievedChunk) -> Citation:
    return Citation(source_id=chunk.source_id, doc_type=DocType(chunk.metadata["doc_type"]), section=chunk.section,
                    product_versions=chunk.metadata["product_versions"], last_updated=chunk.metadata["last_updated"])


def _plain(text: str) -> str:
    return re.sub(r"[*`]", "", text).strip()


def statements(content: str) -> list[str]:
    """Sentences, list items and table rows (rendered as 'Key: header value; ...')."""
    out: list[str] = []
    header: list[str] | None = None
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            header = None
            continue
        if line.startswith("|"):
            cells = [_plain(c) for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if header is None:
                header = cells
                continue
            pairs = [f"{h}: {v}" for h, v in zip(header[1:], cells[1:]) if v]
            out.append(f"{cells[0]}: " + "; ".join(pairs))
            continue
        header = None
        line = re.sub(r"^(\d+\.|[-*])\s+", "", line)
        out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", _plain(line)) if s.strip())
    return out


def _score(statement: str, query_tokens: set[str]) -> int:
    return len(query_tokens & set(tokens(statement)))


def answer_question(message: str, *, retriever: Retriever, account_id: str | None, product_version: str | None,
                    as_of, k: int = 6) -> Answer:
    # 1. Safety guard: instructions aimed at the assistant, or other accounts' data (R8, R10).
    other_ids = {m for m in _ACCOUNT_ID.findall(message) if m != account_id}
    if scan_for_instructions(message) or _OTHER_ACCOUNT.search(message) or other_ids:
        policy = retriever.retrieve("account access another account's data refused", as_of=as_of, k=3)
        cite = [_citation(c) for c in policy.chunks if c.source_id == "KB-POL-005"][:1]
        return Answer(
            AnswerType.REFUSED,
            "I can't help with that. I only discuss the account you're signed in with, I won't share another "
            "customer's information, and I don't follow instructions to ignore my rules."
            + (" [KB-POL-005]" if cite else ""),
            cite,
        )

    # 2. Account-specific facts need account tools (Phase 5): never guess.
    if _OWN_ACCOUNT.search(message):
        if account_id is None:
            return Answer(AnswerType.CLARIFICATION_NEEDED,
                          "To look at your own account I need you to be signed in (the X-Account-Id header). "
                          "Could you sign in and ask again?")
        return Answer(
            AnswerType.NOT_FOUND,
            "I can't confirm that from the evidence I have: I don't have access to your account's records here, so "
            "I won't guess at account-specific details. A person on our team can check your account and follow up.",
        )

    # 3. Retrieval and evidence selection (authoritative documentation only).
    result = retriever.retrieve(message, product_version=product_version, as_of=as_of, k=k)
    evidence = [c for c in result.chunks if c.authority_level <= 2]
    query_tokens = set(tokens(message))
    entities = query_tokens & ENTITIES

    picked: list[tuple[int, int, str, RetrievedChunk]] = []
    for rank, chunk in enumerate(evidence):
        for statement in statements(chunk.content):
            statement_tokens = set(tokens(statement))
            if entities and not entities & statement_tokens:
                continue  # the question names a plan; only use statements about that plan
            score = _score(statement, query_tokens) + _score(chunk.section, query_tokens)
            if score >= MIN_STATEMENT_SCORE:
                picked.append((score, rank, statement, chunk))
    picked.sort(key=lambda item: (-item[0], item[1]))
    floor = max(MIN_STATEMENT_SCORE, picked[0][0] - 2) if picked else MIN_STATEMENT_SCORE

    chosen, seen = [], set()
    for score, _, statement, chunk in picked:
        if score < floor:
            break
        if statement in seen:
            continue
        seen.add(statement)
        chosen.append((statement, chunk))
        if len(chosen) == 3:
            break

    if not chosen:
        return Answer(
            AnswerType.NOT_FOUND,
            "I couldn't find this in the CloudFlow documentation, so I won't guess. I can pass your question to a "
            "person on our support team.",
            retrieved=result.chunks, excluded=result.excluded,
        )

    citations, cited = [], set()
    lines = []
    for statement, chunk in chosen:
        lines.append(f"- {statement.rstrip('.')}. [{chunk.source_id}]")
        if chunk.chunk_id not in cited:
            cited.add(chunk.chunk_id)
            citations.append(_citation(chunk))
    notices = sorted({n for _, c in chosen for n in c.notices})
    text = "According to the CloudFlow documentation:\n" + "\n".join(lines)
    if notices:
        text += "\n\nNote: " + "; ".join(n.replace("deprecation_upcoming:", "this guidance is deprecated from ") for n in notices) + "."
    return Answer(AnswerType.ANSWERED, text, citations, result.chunks, result.excluded)
