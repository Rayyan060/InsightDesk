# InsightDesk Implementation Plan

The authoritative requirements are in the participant guide
([transcription](reference/guide_extract.md)): Sections 3–7 are the contract,
and Section 9 covers judging. Event day is **2026-10-06**. Build windows end in
a code freeze; commit hourly, and every member must commit (Section 5).

| Phase | Scope | Exit criteria | Status |
|---|---|---|---|
| **1. Foundation** | FastAPI app (lifespan, CORS, trace IDs, redacting JSON logs, error envelope, size limits), settings, `/health` with real probes, SQLite engine and sessions, LangGraph state, nodes and wiring, Docker files | Tests pass; live server smoke test | **Done** (103 tests) |
| **2. Database and synthetic data** | Exact Annex C schema and verifier; judge CSV loader; idempotent init; synthetic data pipeline (seeded and LLM) with data-driven edge-case checks; policy registry; account-scoped repositories; typed contracts for the 8 tools; Section 6 / Annex D schema alignment; R8 header-only account; R4 single revision | 256 tests pass; dataset validates 0 errors and 20/20 checks; loader is repeatable | **Done** |
| **3. Knowledge base and Source Register** | 36 articles, 6 policies (KB-POL-001–006, matching the registry), 4 release notes, 27 tickets, 2 community posts; Annex B register; version grammar; Annex A applicability metadata; injection fixtures; seeded and LLM generation; knowledge validator | 0 errors and 0 warnings; 343 tests pass | **Done** |
| **4. Retrieval** | Chunk by section (`section_records`); sentence-transformers embeddings; ChromaDB; filter with `applicability()`; rank by authority then recency; record conflicts; `as_untrusted_data()` in prompts; `POST /ingest` multipart (Markdown or JSON + `SourceRegisterEntry`) with live indexing; `GET /sources` | Retrieval hit rate on version boundaries and the worked examples in source_precedence.md; ingest works live | Next |
| **4b. Agent core** | Ollama client with `MOCK_LLM=true`; R1 structured classifier; grounded answer with citations; critic (`CriticReport`, at most 1 revision); `POST /support` returning the 6.1 response; conversations | End-to-end `/support` tests with a mock LLM | |
| **5. Tools, policy, escalation, audit** | Business logic for the 8 tools (contracts already fixed); Annex A escalation rules in code over the registry; Annex D handoff bundles; `GET /handoffs/{id}`, `GET /audit/{trace_id}`; PII redaction in responses and bundles | Escalation confusion table; no PII leakage | |
| **6. Frontend** | Streamlit chat: citations, tools, critic decision, handoff | Demo script (Section 9.1) | |
| **7. Evaluation** | ≥ 25 labelled requests (Section 7 mix); answer correctness, citation validity, retrieval hit rate, escalation precision and recall, critic agreement, PII leakage, p50/p95 latency and tokens; compare ≥ 2 configurations | Report in the repo | |

## Phase 2 deliverables

| Brief item | Delivered |
|---|---|
| Exact SQLite schema | `database/models.py` (7 tables) and `annex_c.py` verifier; CHECK constraints, FKs, indexes. [database_schema.md](database_schema.md) |
| Initialisation | `scripts/init_db.py` and startup: create-if-missing; reference data with the skip policy; repeatable; never drops data |
| Synthetic dataset | 36 accounts, 96 usage rows, 89 invoices, 6 components. Seed 20261006. All 4 plans, 4 statuses and 3 invoice statuses. [synthetic_data.md](synthetic_data.md), [data_card.md](data_card.md) |
| Pipeline | Generate → validate schema → validate business → export → import (throwaway DB) → row counts → report |
| Scripts | `generate_data`, `validate_data`, `load_accounts`, `init_db`, `inspect_data` (`--export`) |
| Judge loader | `python scripts/load_accounts.py --dir test_accounts/`: headers by name, transactions, FK checks, duplicate and conflict policies, malformed-file safety |
| Policy registry | 23 rules covering refund eligibility, billing disputes, deletion, security, human escalation, tool failure, groundedness, revisions, SLAs, quotas, password reset and cross-account access. Effective-dated and plan-scoped; read-only at runtime |
| Tool interfaces | 8 Annex C tools: typed requests and responses, error codes, account scoping, documented tables, dispatcher. Logic in Phase 5 |
| Security | Bound parameters; account-scoped repositories; no PII in logs or reports; masked emails in the CLI |

## Conflicts with Phase 1, found and resolved in Phase 2

| Phase 1 | Guide | Resolution |
|---|---|---|
| Accepted a body `account_id` (header takes precedence) | R8: account **only** from `X-Account-Id` | Body field and resolver removed; Phase 1 tests replaced by an "ignored" test |
| `MAX_CRITIC_REVISIONS=2` | R4: at most one revision | Default 1, maximum 1; registry rule `CRITIC-REVISIONS-01` |
| Provisional response: free-text intent, structured `ToolInvocation(tool_name, status)`, critic verdict pass/revise/fail | Section 6.1: intent object, `{"tool","output"}`, critic scores with decision answer/revise/escalate, `as_of_date`, Annex D `handoff` | Schemas rewritten; the guide's own JSON examples are tests |
| Request without `channel` and `product_version` | Section 6 body | Added |
| 5 tool stubs with different names | 8 named tools (Annex C) | Replaced |
| Provisional handoff status/priority models | Annex C `handoffs` and Annex D bundle | Replaced |
| `/health` reported `pending_annex_c` | Annex C available | Reports `matches_annex_c` and row counts |

## Phase 3 deliverables

| Brief item | Delivered |
|---|---|
| Policy articles KB-POL-001–006 | Sections equal the registry's `source_section`. Numeric values are stated in the cited sections, and KB-POL-002's table equals plan_limits.csv (validated) |
| Help-center articles | 36 across the 5 Annex F categories, including the guide's example IDs (KB-ADV-007, KB-API-014, KB-BIL-003) |
| Resolved tickets | 27 (4 angry, 6 outdated or contradicting, 16 useful history, 1 injection fixture) |
| Version-aware content | Versions 3.8–4.3; 17 version-specific sources; export comes in three versions |
| Deprecated, outdated, conflicting | 2 deprecations in effect, 1 upcoming (RN-2026-09), 2 supersessions, 8 sources with recorded conflicts |
| Prompt-injection data | COM-0001, COM-0002, TKT-2026-0240; detector and untrusted-data wrapper; tests that documents can't change policy |
| Source Register | `data/source_register/source_register.csv`, exactly the Annex B columns; single metadata model shared with `/ingest` and `/sources` |
| Validation | `scripts/validate_knowledge.py`: every check in the brief plus the Section 4.1 minimums; exits non-zero on errors |
| Generation | `scripts/generate_knowledge.py --generator seeded|llm`, reproducible; prompts, manifest and attempt log |
| Docs | knowledge_base.md, source_precedence.md, data card (KB section), architecture |

## Open items and blockers

1. **LLM data (Sections 4.1 and 4.2): done, with fallbacks.** Real qwen2.5:7b
   runs:
   * **accounts:** 4 of 36 are LLM-filled; 32 fell back to seeded data after
     duplicate-email rejections;
   * **knowledge base:** 65 of 75 sources are LLM-rewritten; 7 fell back; 3
     fixtures are verbatim.

   Improving the account prompt to avoid generic emails would raise LLM
   coverage. See the [data card](data_card.md).
2. **Demo flow** ([demo.md](demo.md)): ChromaDB ingestion, version-aware
   retrieval with authority ranking, extractive grounded `/support`,
   `/sources`, and a Streamlit console.
3. **Docker** has not been built: there's no Docker on the build machine.
4. **Git.** Not initialised. The guide requires a repository, commits from all
   members and a `final` tag.
5. **Reference date.** Relative edge cases assume `as_of_date = 2026-10-06`.
   Evaluation requests should send it explicitly.
