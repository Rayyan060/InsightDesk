# Data Card: InsightDesk Synthetic Data

Annex E template, applied to the [customer accounts](#customer-accounts) and
the [knowledge base](#knowledge-base). All figures come from the committed run
records:

* `data/synthetic/generation_manifest.json` and `validation_report.md`;
* `data/source_register/kb_manifest.json`, `kb_llm_attempts.json` and
  `knowledge_validation_report.md`.

## Record provenance at a glance

| Dataset | LLM-generated | LLM-rewritten | Deterministic seeded (fallback) | Verbatim / hand-authored |
|---|---|---|---|---|
| Accounts (36) | 4 accounts: A1001, A1002, A1003, A1015 (+12 usage rows, 19 invoices) | — | 32 accounts (+84 usage rows, 70 invoices) | — |
| Platform status (6 rows) | 6 (timestamps from the LLM; statuses and incidents fixed) | — | — | — |
| Reference data | — | — | — | `plan_limits` (4) and `policy_registry` (23), hand-authored |
| Knowledge base (75) | — | 65 (31 articles, 5 policies, 3 release notes, 26 tickets) | 7 (KB-POL-003, KB-ACC-001, KB-API-014, KB-TRB-002, KB-TRB-004, KB-TRB-006, RN-2026-02) | 3 adversarial fixtures (COM-0001, COM-0002, TKT-2026-0240) |

* **LLM-generated:** the model chose the values, within a schema and with
  every invariant fixed by code (IDs, dates, amounts, statuses, boundary
  values).
* **LLM-rewritten:** the model rewrote the prose of specs authored with an AI
  coding assistant. It cannot add or drop facts (enforced), so no fact
  originates from the LLM.
* **Fallback:** when a model output still failed validation after 3 attempts,
  the record was produced by the deterministic seeded generator instead. Each
  record's provenance says which.

**The corpus is not entirely LLM-generated.**

## Customer accounts

| Field | Content |
|---|---|
| **Purpose** | Test data for the deterministic tools and the escalation policy: quota boundaries, failed and duplicate payments, refund-window boundaries, suspended, cancelled and past_due accounts, upgrades, legacy versions. Fixed Annex C schema |
| **Generator** | `llm`. Model **qwen2.5:7b** (Ollama), **temperature 0.2**, **seed 20261006** (per account: `seed + index × 10`, plus the attempt number), **reference date 2026-10-06**, **prompt version v1**. Run at 2026-10-06T09:19:08Z: **105 LLM calls**, 135,036 prompt tokens and 48,920 completion tokens |
| **Prompts** | Verbatim in [`data/synthetic/prompts/`](../data/synthetic/prompts/): `accounts_system_v1.md`, `account_bundle_v1.md`, `platform_status_system_v1.md`, `platform_status_v1.md` |
| **Schema enforcement** | (1) Ollama structured output with the `AccountBundle` JSON schema. (2) Annex C row models. (3) Blueprint conformance: every FIXED value must match exactly, and emails must be unique. (4) Up to 3 attempts with the problems fed back. (5) Otherwise, **fallback to the deterministic seeded filler** (`fill_seeded` with `Random(seed + index)`), recorded in `fell_back_to_seeded`. (6) SQLite CHECK and FK constraints on import |
| **Acceptance** | 37 targets (36 accounts + platform status). **5 accepted:** 2 on the first try (A1001, platform status), 3 after retry (A1002 and A1015 on attempt 2, A1003 on attempt 3). **32 fell back** to seeded data (A1004–A1014, A1016–A1036). Attempts: 5 accepted, 97 conformance errors, 3 schema errors |
| **Row counts and distributions** | 36 accounts:<br>• Free 9, Pro 13, Business 8, Enterprise 6;<br>• active 27, past_due 3, suspended 2, cancelled 4;<br>• versions 4.3 × 22, 4.2 × 6, 4.1 × 3, 4.0 × 2, 3.9 × 2, 3.8 × 1.<br>96 usage rows (3 months × 32). 89 invoices (paid 81, failed 7, refunded 1; USD 87, INR 2). 6 platform components |
| **Edge cases included** | All 20 checks pass, verified from the data. The carrier accounts are the same as in [synthetic_data.md](synthetic_data.md#edge-cases-verified-from-the-data), for example A1003 exactly at the run limit, A1004 one over, A1010 duplicate charge, A1011 and A1012 refund-window boundaries. Pinned boundary values hold for LLM-filled accounts too (A1003's 20,000 runs) |
| **Validation results** | Report written at generation time ([`validation_report.md`](../data/synthetic/validation_report.md)): **0 errors, 1 warning**. The warning is `policy_source_unverified`, because the Source Register wasn't present in that run's environment. **Re-validated now** with `scripts/validate_data.py --no-report`: **0 errors, 0 warnings**, 20/20 edge-case checks |
| **What the LLM got wrong** | **Rejected by the pipeline:**<br>• every one of the 97 conformance rejections included a **duplicate `owner_email`**: the model kept reusing generic addresses;<br>• 18 failed invoices without a `failure_reason`;<br>• 10 changed pinned usage values;<br>• 3 invalid `product_version` formats and 1 changed `product_version`.<br>**Present in accepted output:**<br>• **generic placeholder emails** (`john.doe@example.com`, `jane.doe@example.com`, `jane.smith@example.com`, `support@fictionaltechinc.example.com`);<br>• **generic company names**, with a **duplicate: "FictionalTech" on both A1002 and A1003** (company names have no uniqueness rule, so it passed), plus "TechSolve Inc" and "FictionalTech Inc";<br>• round-number usage values (5000, 7000, 120000);<br>• platform timestamps exactly on the hour |
| **Known limitations** | Only 4 of 36 accounts are LLM-filled. The fallback filler gives each account its own RNG stream, which caused two more duplicate company names: "Lumenary Health" (A1005, A1030) and "Sablewood Studios" (A1019, A1036). LLM free-text fields are protected by schema validation only; they can't be byte-reproduced (fallback rows can, and are tested). Monthly aggregates only; flat pricing; a fixed INR rate. Edge cases are anchored to `as_of_date = 2026-10-06` |

## Knowledge base

Full details: [knowledge_base.md](knowledge_base.md) and [source_precedence.md](source_precedence.md).

| Field | Content |
|---|---|
| **Purpose** | Retrieval corpus for grounded, cited answers (R2, R3). It must exercise version matching, deprecations, supersession, documentation-over-ticket precedence (Annex A), not-covered questions and prompt-injection resistance (R10) |
| **Generator** | `llm` (rewrite mode). Model **qwen2.5:7b**, **temperature 0.2**, **seed 20261006**, **prompt version v1**, spec version v1, **reference date 2026-10-06**. Run at 2026-10-06T09:44:24Z: **97 LLM calls**, 57,356 prompt tokens and 17,926 completion tokens. The input specs (`backend/app/knowledge/catalog/`) were authored with an AI coding assistant |
| **Prompts** | [`data/synthetic/prompts/kb_system_v1.md`](../data/synthetic/prompts/kb_system_v1.md), `kb_document_v1.md`, `kb_ticket_v1.md`. These improve on the Annex F starter: versions, facts that must be kept, a ban on new facts, safety rules, and per-section JSON output |
| **Schema enforcement** | JSON schema (`DocumentRewrite` / `TicketRewrite`); identical headings; every spec fact kept (error codes, versions, numbers, KB IDs, `code`, **UI labels**); no new codes, versions, IDs or URLs; no assistant-addressed text. Up to 3 attempts, then **fallback to the deterministic seeded render** |
| **Acceptance** | 75 sources:<br>• **65 rewritten**: 55 on the first try, 10 after retry;<br>• **7 fell back** to seeded after 3 rejected attempts;<br>• **3 fixtures** rendered verbatim and never sent to the model.<br>Attempts: 65 accepted, 32 conformance errors |
| **Counts and distributions** | 36 articles (getting started 4, account and billing 8, API and integrations 9, troubleshooting 7, advanced 8), 6 policies, 4 release notes, 27 tickets, 2 community posts. Versions 3.8–4.3; 17 version-specific sources |
| **Edge cases included** | Deprecations in effect: KB-ADV-003, TKT-2025-0414. Upcoming: KB-API-002 (RN-2026-09). Supersessions: KB-API-009 → KB-API-014, KB-ADV-003 → KB-ADV-004. 6 outdated or contradicting tickets, 4 angry complaints, 3 injection fixtures. Not covered: SAP Ariba, Oracle NetSuite, on-premises |
| **Validation results** | `scripts/validate_knowledge.py`: **0 errors, 0 warnings**. Provenance-aware reproducibility tests: seeded and fixture files byte-identical; rewritten files keep metadata, headings and every fact, bound to their table rows. 25 mutation tests prove the checks fire |
| **What the LLM got wrong** | **Rejected by the pipeline (32 attempts):**<br>• 43 missing-fact problems (dropped numbers, error codes, **UI paths**);<br>• 8 invented facts (for example adding CF-503 or CF-504);<br>• **3 attempts added text addressed to an assistant**;<br>• 1 changed heading set and 1 dropped bold deprecation date.<br>**Present in accepted output:**<br>• KB-ADV-008's table **turned into a bullet list** (the prompt said to keep tables; values stay correctly paired);<br>• KB-POL-002 writes `1,499` as `1499` (same value);<br>• cosmetic punctuation changes (for example KB-POL-001's Oxford comma) and header capitalisation |
| **Known limitations** | Prose is LLM-rewritten; facts come from AI-assistant-authored specs. Short articles; English only; single-turn tickets; the injection detector is heuristic. All content is fictional and contains no real secrets |
