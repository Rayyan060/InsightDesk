# InsightDesk

InsightDesk is an agentic AI customer-support system for the **HCLTech Future
Ready AI Engineer Hackathon, Use Case 2**. It answers from a version-aware
knowledge base, reads account data through deterministic tools, critiques its
own drafts, escalates to humans according to explicit policies, and records
an audit trail for every turn.

> **Current status: Phase 3 complete (knowledge base and Source Register).**
>
> * **Phase 1:** API skeleton, configuration, redacting logs, health checks and
>   agent-graph wiring.
> * **Phase 2:**
>   * the exact **Annex C** SQLite schema;
>   * a validated **synthetic dataset** (36 accounts covering every Section 4.2
>     edge case);
>   * the **judge CSV loader** (`scripts/load_accounts.py`);
>   * the **policy registry**;
>   * typed contracts for the **eight required tools**;
>   * request and response schemas aligned with the guide's Section 6.
> * **Phase 3:**
>   * the **CloudFlow knowledge base**: 36 help-center articles, 6 policy
>     articles, 4 release notes, 27 resolved tickets and 2 community posts;
>   * the Annex B **Source Register**;
>   * Annex A **precedence metadata** (version, date, deprecation and
>     supersession applicability);
>   * **prompt-injection fixtures** treated as data;
>   * a knowledge validator (**0 errors, 0 warnings**).
>
> **Demo flow:** `POST /support` now answers from the knowledge base:
>
> * ChromaDB retrieval, version-aware, with authority ranking;
> * extractive answers with `[SOURCE-ID]` citations;
> * refusals for injection or cross-account requests;
> * "not enough evidence" for questions about the customer's own records.
>
> `GET /sources` returns the Source Register. See [docs/demo.md](docs/demo.md)
> and [Current limitations](#current-limitations).
>
> The official requirements are in `docs/reference/participant_guide.pdf`
> (kept locally, gitignored), with a transcription in
> [docs/reference/guide_extract.md](docs/reference/guide_extract.md).

## Architecture summary

```
Client (Streamlit / eval) ──► FastAPI
                               ├─ middleware: trace ID · CORS · body-size limit
                               ├─ routes: /health /support /ingest /sources /handoffs /audit /conversations
                               └─ LangGraph workflow
                                    validate → classify → retrieve / tools → generate ⇄ critique
                                    → policy → (escalate) → audit
                                       │            │             │
                                    ChromaDB     SQLite        Ollama
```

Where to read more:

* Architecture, with Mermaid diagrams: [docs/architecture.md](docs/architecture.md)
* API and tool contract: [docs/api_contract.md](docs/api_contract.md)
* Database: [docs/database_schema.md](docs/database_schema.md)
* Synthetic data: [docs/synthetic_data.md](docs/synthetic_data.md) and the
  [data card](docs/data_card.md)
* Knowledge base: [docs/knowledge_base.md](docs/knowledge_base.md)
* Source precedence and "knowledge is data": [docs/source_precedence.md](docs/source_precedence.md)
* Roadmap: [docs/implementation_plan.md](docs/implementation_plan.md)

## Technology stack

| Layer | Technology |
|---|---|
| API | Python 3.11+, FastAPI, Uvicorn, Pydantic v2, pydantic-settings |
| Persistence | SQLAlchemy 2.x, SQLite (foreign keys enforced) |
| Orchestration | LangGraph |
| LLM | Ollama (local; model configurable, default `qwen2.5:7b`) |
| Retrieval | ChromaDB (persistent), sentence-transformers (`all-MiniLM-L6-v2`) |
| Frontend | Streamlit (Phase 6) |
| Ops | Docker, Docker Compose, pytest, structured JSON logging |

## Repository layout

```
insightdesk/
├── backend/
│   ├── app/
│   │   ├── main.py              # app factory, lifespan, middleware, routers
│   │   ├── core/                # config, logging, security, exceptions, middleware, lifecycle
│   │   ├── api/                 # routes/ + dependencies.py
│   │   ├── schemas/             # support, tools, handoff, ingestion, health, common
│   │   ├── database/            # models (Annex C), annex_c verifier, row_schemas, validation,
│   │   │                        #   csv_io (loader/export), init_db, repositories/ (account-scoped)
│   │   ├── agents/              # state.py, graph.py, nodes/
│   │   ├── rag/                 # ingestion, chunking, embeddings, retriever, precedence, vector_store
│   │   ├── tools/               # the 8 Annex C tools + registry/dispatcher (logic: Phase 5)
│   │   ├── synthetic/           # scenarios, seeded + LLM generators, edge-case checks, pipeline
│   │   ├── knowledge/           # catalog/ (KB specs), documents, versions, precedence, safety, generator, validation
│   │   ├── cli/                 # load_accounts, init_db, generate_data, validate_data, inspect_data, *_knowledge
│   │   ├── services/            # llm (Ollama), policy, audit, health
│   │   └── utils/
│   ├── tests/
│   ├── requirements.txt / requirements-dev.txt
│   ├── pyproject.toml           # pytest config
│   └── Dockerfile
├── frontend/app.py              # placeholder (Phase 6)
├── data/
│   ├── reference/               # plan_limits.csv, policy_registry.csv (hand-authored)
│   ├── synthetic/               # accounts/usage/invoices/platform_status CSVs, prompts/, validation report
│   ├── knowledge_base/          # articles/ policies/ release_notes/ community/ (Markdown)
│   ├── tickets/                 # resolved tickets (JSON, Annex F fields)
│   ├── source_register/         # source_register.csv (Annex B), kb_labels.csv, validation report
│   └── evaluation/              # Phase 7
├── scripts/                     # load_accounts, init_db, generate/validate/inspect_data, generate/validate/inspect_knowledge
├── docs/
├── docker-compose.yml
└── .env.example
```

## Prerequisites

* Python **3.11 or newer** (developed and tested on 3.12.0)
* About 3 GB of free disk space for dependencies (PyTorch is pulled in by sentence-transformers)
* [Ollama](https://ollama.com/download), for LLM features. It isn't needed to
  run the Phase 1 tests.
* Optional: Docker Desktop, or Docker Engine with Compose v2

## Installation

From the repository root (`insightdesk/`):

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS/Linux:         source .venv/bin/activate
pip install -r backend/requirements-dev.txt
```

## Environment setup

```bash
cp .env.example .env        # Windows: Copy-Item .env.example .env
```

* All settings have safe defaults, so `.env` is optional.
* Relative paths (`./data/...`) resolve against the **project root**, whatever
  the current directory is.
* If `DATABASE_URL`, `OLLAMA_BASE_URL` or `CHROMA_PERSIST_DIR` is blank, that
  component is reported as `not_configured`.
* An invalid value (for example `LOG_LEVEL=LOUD` or `API_PORT=abc`) stops
  startup with an error that names the field without echoing the value.
* Choose an Ollama model that fits your hardware, for example:

  ```bash
  ollama pull qwen2.5:7b       # ~5 GB, 16 GB RAM recommended
  # or, on smaller machines:
  ollama pull qwen2.5:3b       # then set OLLAMA_MODEL=qwen2.5:3b
  ```

## Data: database, synthetic accounts and the judge loader

```bash
python scripts/init_db.py --with-synthetic        # Annex C schema + reference data + our 36 accounts
python scripts/load_accounts.py --dir test_accounts/   # load judge CSVs (accounts.csv, usage.csv, invoices.csv, ...)
python scripts/validate_data.py                   # re-validate data/synthetic, write validation_report.md
python scripts/generate_data.py --generator llm --force   # regenerate with Ollama (default: seeded)
python scripts/inspect_data.py --account A1010    # inspect one account (email masked)
```

* All of these are safe to repeat: nothing is dropped, and re-importing the
  same data is a no-op.
* The loader never overwrites a different existing record unless you pass
  `--on-conflict overwrite --allow-overwrite`.
* The API also creates the schema and loads the reference data at startup
  (`SEED_REFERENCE_DATA=true`).
* Inside Docker, use
  `docker compose exec backend python -m app.cli.load_accounts --dir /app/data/<dir>`.

## Knowledge base

```bash
python scripts/validate_knowledge.py                           # exit 1 on any error
python scripts/inspect_knowledge.py --version 3.9 --as-of 2026-10-06   # which sources apply, and why not
python scripts/inspect_knowledge.py --export-jsonl kb_sections.jsonl   # retrieval-ready section records
python scripts/generate_knowledge.py --force                   # regenerate (seeded); --generator llm for Ollama
```

## Running the FastAPI server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

* Swagger UI: <http://localhost:8000/docs>
* Health: <http://localhost:8000/health>

```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/support \
     -H "Content-Type: application/json" -H "X-Account-Id: A1010" \
     -d '{"message": "Why was I charged twice?", "channel": "web", "as_of_date": "2026-10-06"}'
# -> 501 {"error": {"code": "not_implemented", ...}, "trace_id": "..."}
```

## Running tests

```bash
cd backend
python -m pytest            # add -v for per-test output
```

The tests use temporary SQLite and Chroma directories and mocked Ollama HTTP
responses, so neither Ollama nor network access is needed.

## Docker startup

> The Docker files are written but **haven't been built yet**: the development
> machine has no Docker. See the limitations below.

**Ollama on the host (recommended):**

```bash
ollama serve                       # on the host
docker compose up --build
```

The backend reaches the host at `http://host.docker.internal:11434`. Compose
adds a `host-gateway` mapping so this also works on Linux.

**Ollama in a container:**

```bash
OLLAMA_BASE_URL=http://ollama:11434 docker compose --profile ollama up --build
docker compose exec ollama ollama pull qwen2.5:7b
```

* SQLite, Chroma and the embedding-model cache persist in `./data`, which is
  mounted at `/app/data`.
* The container health check calls `/health/live`. It doesn't use `/health`,
  because Ollama being down shouldn't make the API container look dead.
* The image installs CPU-only PyTorch.

## Security notes

* `X-Account-Id` is declared context, **not authentication**. The prototype
  doesn't authenticate users.
* The account comes **only** from `X-Account-Id` (R8). The request body has no
  account field.
* Account data is reachable only through `AccountScopedRepository`, which takes
  the request's account context and has no method that accepts an account ID.
  Tool request models reject an `account_id` argument.
* Refunds, credits and account changes are never executed: no tool writes
  anything except `create_handoff`. Password-reset results can't carry a token
  or link.
* The policy registry is read-only at runtime; the LLM can't create or change rules.
* Logs are JSON, carry a trace ID, and are redacted. Customer messages,
  account IDs, credentials, emails, phone numbers and card-like numbers are
  removed or masked. Uvicorn's access log is disabled because it records
  query strings.
* Error responses never echo submitted values.

## Current limitations

1. **Only the minimal demo flow is live.**
   * `/support` and `/sources` work.
   * `/ingest`, `/handoffs`, `/audit` and `/conversations` return **501**; use
     `scripts/ingest_knowledge.py` for ingestion.
   * The eight tools have typed contracts but return `not_implemented` until
     Phase 5.
   * Graph nodes other than `validate_input` raise `NodeNotImplementedError`.
2. **LLM data with seeded fallbacks.** Both committed datasets come from real
   qwen2.5:7b runs (2026-10-06), and invalid generations fell back to
   deterministic seeded data:
   * **accounts:** 4 of 36 are LLM-filled, and 32 fell back;
   * **knowledge base:** 65 of 75 sources are LLM-rewritten, 7 fell back, and
     3 fixtures are verbatim.

   Known LLM mistakes include generic emails and a duplicate company name. See
   the [data card](docs/data_card.md).
3. **The demo answers extractively.** `/support` answers from retrieved
   documentation with citations ([docs/demo.md](docs/demo.md)). Ollama
   generation, intent, critic, tools and escalation are not wired in yet.
4. **Docker hasn't been verified.** The Docker files haven't been built or run.
5. **Ollama hasn't been tested live.** The health probe was tested with mocked
   responses and against an unreachable endpoint only.
6. **No authentication, rate limiting or migrations.** `X-Account-Id` is
   declared context, as the guide specifies.
7. **Git.** The guide requires a Git repository with commits from every member
   and a `final` tag. The workspace isn't a Git repository yet.

## Next development phase

**Phase 4: Retrieval.**

* Embed `section_records()` with sentence-transformers and index them in
  ChromaDB.
* Filter candidates with `applicability()`, then rank by authority and
  recency (Annex A.2 steps 3–4), recording conflicts.
* Wrap document text with `as_untrusted_data()`.
* Implement `POST /ingest` as multipart (Markdown article or JSON ticket +
  `SourceRegisterEntry` metadata), with live indexing.
* Implement `GET /sources`.

See [docs/implementation_plan.md](docs/implementation_plan.md).
