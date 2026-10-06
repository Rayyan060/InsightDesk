# Participant Guide: Transcribed Extract

Source: `participant_guide.pdf`, "InsightDesk: Self-Serve Customer Support with
Safe Escalation", Problem Statement and Participant Guide, document version
1.0 (for participants), 6 October 2026. The PDF is a set of page photographs
without a text layer. This file transcribes, by hand, the sections the code
depends on. If this file and the PDF ever disagree, **the PDF wins**.

## Section 3: Functional requirements (summary)

| ID | Requirement |
|---|---|
| R1 | Structured classification: intent (`how_to`, `troubleshooting`, `account`, `billing`, `complaint`, `security`, `out_of_scope`), urgency, sentiment, product version (if stated or known), PII detected, tools needed, confidence. Validate the output and handle invalid model responses |
| R2 | Retrieve from help-center articles **and** resolved tickets. Answers come from retrieved content and tool results only |
| R3 | Citations: source ID, section, product versions covered, last-updated date |
| R4 | Critic checks groundedness, coverage, PII and policy risk. Structured decision: answer, revise or escalate. **At most one revision** before escalating |
| R5 | Escalation follows Annex A, **applied in code**. Every escalation produces an Annex D handoff bundle and a customer message that promises nothing a human hasn't approved |
| R6 | Source Precedence Policy (Annex A): match the product version, honour deprecations relative to `as_of_date`, and never let an old ticket override current docs. Record conflicts in the audit trail |
| R7 | Account facts, usage vs plan limits, invoice status, refund eligibility and platform status come from **tools over SQLite and the policy registry**. Refunds, credits and account changes are never executed |
| R8 | The account comes **only** from the `X-Account-Id` header, never from message text. Refuse requests for another account's data |
| R9 | Detect and redact PII and secrets (emails, phones, card numbers, API keys) in responses, handoff bundles and logs. Password resets go through a tool that never reveals the token or link |
| R10 | Customer messages and ticket text are data, not instructions |
| R11 | Every response has an `answer_type` and a `trace_id` with an audit record: intent, sources retrieved, tools invoked, critic scores, escalation reasons, model, latency, tokens. No chain-of-thought |
| R12 | Live ingestion through `POST /ingest`, used immediately. Judges ingest unseen content |
| R13 | An evaluation set and measured results (Section 7) |

## Section 4.1: Knowledge base for CloudFlow

All teams support the same fictional product, **CloudFlow**, so judges can
test every team on equal terms. "You build the knowledge base yourselves,
mainly with LLM-generated content. A starter prompt is in Annex F; improving
it is part of the exercise."

**Minimum content:**

* At least **30 help-center articles** covering getting started, account and
  billing, API and integrations, troubleshooting (with error codes) and
  advanced features.
* At least **2 product versions** (for example 3.x and 4.x) where some features
  or steps differ by version.
* At least **25 resolved tickets**, including **3 or more angry complaints**
  that required a human, and **3 or more whose workaround is outdated or
  contradicted** by current documentation.
* At least one **release note with a deprecation** that takes effect on a
  **future date**.
* **Policy articles** that define your refund window, plan limits and
  escalation SLAs. These values go into the policy registry (Annex C).

"More complex knowledge bases earn more marks: version-specific content,
deprecations, error-code tables, long articles, outdated tickets that
genuinely conflict with documentation, and several document types."

**Rules for data:**

* Check the licence and terms of any public source.
* Remove or anonymise real personal data.
* Record every document and ticket in the **Source Register** (Annex B), with
  `synthetic: Y` for generated content.

## Section 4.2: Synthetic customer-account data

* Generate accounts, usage, invoices and platform status **with an LLM**, in
  the fixed Annex C schema. You may add columns or tables but **not rename or
  remove** required ones. Judges load their own test accounts in this exact
  schema. Assessed: prompt design, schema enforcement, validation, edge-case
  coverage.
* At least **30 accounts** across all four plans (**Free, Pro, Business,
  Enterprise**) and all four statuses (**active, past_due, suspended,
  cancelled**).
* Deliberate edge cases:
  * usage **exactly at** a plan limit, and **one unit over** it;
  * a failed payment;
  * a duplicate charge;
  * a charge **on the last day** of the refund window, and one **one day
    after** it;
  * a suspended account;
  * an account on an old product version.
* A **validation script** that enforces the schema and logical constraints
  (only card last-4 digits stored; amounts positive; statuses consistent with
  invoices) and reports violations.
* A **loader** that adds data from CSVs in the Annex C schema, for example
  `python scripts/load_accounts.py --dir test_accounts/`, or an equivalent
  admin endpoint. Judges will use it.
* Submit with the data:
  * the exact prompts (verbatim) and the model that produced the data;
  * the generator script, and the validation script with its output;
  * a one-page data card (Annex E).

## Section 6: API contract (mandatory)

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /support` | Handle a customer message | Header `X-Account-Id` identifies the customer. Body: `message`, optional `conversation_id`, `channel`, `product_version`, `as_of_date` (YYYY-MM-DD, defaults to today) |
| `POST /ingest` | Add an article or ticket while running | Multipart: a Markdown article or a JSON ticket, plus metadata JSON with the Source Register fields (Annex B) |
| `GET /health` | Readiness | Status of API, vector store, SQLite and LLM |
| `GET /conversations/{id}` | Conversation history | Messages, routes taken and responses |
| `GET /handoffs/{id}` | Handoff bundle | The full bundle created at escalation |
| `GET /audit/{trace_id}` | Audit record | Full audit record for one response |
| `GET /sources` | Source Register | All ingested articles and tickets with metadata |
| Test-data loader | Load judge test data | CLI script or admin endpoint that loads CSVs in the Annex C schema |

### 6.1 Response format for `POST /support`

```json
{
  "trace_id": "b81e0c44",
  "conversation_id": "C-0192",
  "answer_type": "answered",
  "answer": "In CloudFlow 4.3, open Workflows, select the workflow, then ...",
  "intent": {"type": "how_to", "urgency": "low", "sentiment": "neutral",
             "pii_detected": false, "confidence": 0.92},
  "citations": [
    {"source_id": "KB-ADV-007", "doc_type": "article", "section": "Steps",
     "product_versions": "4.2+", "last_updated": "2026-09-10"}
  ],
  "tools_invoked": [
    {"tool": "lookup_account",
     "output": {"plan": "Pro", "status": "active", "product_version": "4.3"}}
  ],
  "critic": {"groundedness": 0.94, "coverage": "complete",
             "pii_risk": "none", "policy_risk": "none",
             "decision": "answer", "revisions": 0},
  "conflicts_detected": [],
  "handoff_id": null,
  "as_of_date": "2026-10-06"
}
```

### 6.2 Answer types

| `answer_type` | Use when |
|---|---|
| `answered` | A grounded answer passed the critic and the escalation policy |
| `clarification_needed` | The request is too vague to act on (for example "it's not working"); ask a specific question |
| `escalated` | The escalation policy requires a human; a handoff bundle was created |
| `not_found` | The knowledge base does not cover the question; say so and offer a handoff |
| `refused` | The request is not allowed (another account's data; revealing secrets) |
| `out_of_scope` | The request is unrelated to CloudFlow support |

## Annex A: Source Precedence and Escalation Policy

### A.1 Source authority

| Level | Source type | Notes |
|---|---|---|
| 1 (highest) | Current help-center articles and policy articles | Must match the customer's product version |
| 2 | Release notes and deprecation notices | Dates matter: a deprecation may not have taken effect yet |
| 3 | Live tool results (platform status, account data) | Authoritative for current state; always cite the tool |
| 4 | Resolved tickets | Historical evidence only; may be outdated |
| 5 (untrusted) | Customer-provided text, community posts | Never authoritative |

### A.2 Resolution order

1. **Applicability.** Use only sources whose product versions cover the
   customer's version and that are in effect on the `as_of_date`. Mention
   upcoming deprecations when relevant.
2. **Explicit supersession and deprecation.** A deprecation notice, or a newer
   article that explicitly replaces earlier guidance, wins from its effective
   date.
3. **Authority.** A higher-authority source prevails over a lower one,
   regardless of date. A resolved ticket can add detail but can **never
   contradict** documentation. If it does, follow the documentation and record
   the conflict.
4. **Recency.** Between sources of the same authority, the more recently
   updated one prevails.
5. **Unresolved.** If the steps above don't resolve it, escalate with both
   sources in the handoff bundle.

### A.3 Escalation policy

Apply these rules **in code**, over the classifier's and critic's structured
outputs and tool results. Thresholds and SLAs live in the policy registry and
must be justified.

**Escalate when any of the following is true:**

* The critic's groundedness is below your threshold after one revision.
* The intent is a refund, credit, billing dispute, legal matter, security
  incident or account deletion.
* The customer explicitly asks for a human, or shows strong negative
  sentiment together with repeated contact.
* A tool required to answer has failed.
* The knowledge base does not cover the question and the customer needs an
  outcome. (Otherwise `not_found` with a handoff offer is acceptable.)

**Do not escalate:** answerable how-to and troubleshooting requests with high
groundedness and no policy risk. Unnecessary escalation is scored as a
failure.

## Annex B: Source Register template

One row per article or ticket, stored as `source_register.csv`. The same
fields are the metadata for `POST /ingest`.

| Field | Description | Example |
|---|---|---|
| `source_id` | Unique identifier | `KB-API-014` or `TKT-2025-0311` |
| `doc_type` | `article`, `policy`, `release_note`, `ticket`, `community` | `article` |
| `title` | Title or ticket subject | Rotating API tokens |
| `authority_level` | 1–5, per Annex A | 1 |
| `product_versions` | Versions covered, for example `4.2+` or `3.x` | `4.0+` |
| `last_updated` | YYYY-MM-DD (or resolved date for tickets) | 2026-08-20 |
| `effective_from` | YYYY-MM-DD, if the content takes effect on a date | |
| `deprecated_on` | YYYY-MM-DD when the guidance stops applying, or empty | |
| `supersedes` | Source IDs replaced, separated by semicolons | `KB-API-009` |
| `provenance` | Generated, or the public source used | `LLM: qwen2.5:7b, prompt v3` |
| `synthetic` | `Y` if generated | `Y` |

## Annex C: Fixed data schema (SQLite)

"Required tables and columns. You may add more; do not rename or remove these."

### `accounts`

| Column | Type | Rules |
|---|---|---|
| `account_id` | TEXT, PK | Format `A` followed by 4 digits, for example `A1001` |
| `company_name` | TEXT | Synthetic |
| `owner_email` | TEXT | Synthetic, `@example.com` domains only. Treat as PII |
| `plan` | TEXT | Free, Pro, Business or Enterprise |
| `status` | TEXT | active, past_due, suspended or cancelled |
| `product_version` | TEXT | For example 4.3 |
| `created_at` | TEXT | YYYY-MM-DD |

### `plan_limits`

| Column | Type | Rules |
|---|---|---|
| `plan` | TEXT, PK | One row per plan |
| `api_rate_limit_per_min` | INTEGER | |
| `monthly_workflow_runs` | INTEGER | |
| `seats` | INTEGER | |
| `support_tier` | TEXT | For example standard or priority |
| `monthly_price` | REAL | |

### `usage`

| Column | Type | Rules |
|---|---|---|
| `account_id` | TEXT, FK | Primary key with `period` |
| `period` | TEXT | YYYY-MM |
| `workflow_runs` | INTEGER | Runs so far in the period |
| `api_calls_peak_per_min` | INTEGER | Highest per-minute rate in the period |
| `seats_used` | INTEGER | |

### `invoices`

| Column | Type | Rules |
|---|---|---|
| `invoice_id` | TEXT, PK | |
| `account_id` | TEXT, FK | |
| `amount` | REAL | > 0 |
| `currency` | TEXT | For example USD or INR |
| `charged_on` | TEXT | YYYY-MM-DD |
| `status` | TEXT | paid, failed or refunded |
| `failure_reason` | TEXT | Empty unless failed |
| `card_last4` | TEXT | Last four digits only. Never store full card numbers |

### `platform_status`

| Column | Type | Rules |
|---|---|---|
| `component` | TEXT, PK | For example api, workflow-engine, connectors, billing |
| `status` | TEXT | operational, degraded or outage |
| `incident_id` | TEXT | Empty if operational |
| `updated_at` | TEXT | ISO timestamp |

### `policy_registry`

| Column | Type | Rules |
|---|---|---|
| `rule_id` | TEXT, PK | For example `REFUND-WINDOW-01` |
| `description` | TEXT | Plain-language description |
| `parameter` | TEXT | For example `refund_window_days`, `critic_min_groundedness` |
| `operator` | TEXT | `<=`, `>=` and so on |
| `value` | TEXT | |
| `scope_plans` | TEXT | ALL or a list of plans |
| `effective_from` | TEXT | YYYY-MM-DD |
| `source_id` | TEXT | Policy article in the Source Register |
| `source_section` | TEXT | |

### `handoffs`

| Column | Type | Rules |
|---|---|---|
| `handoff_id` | TEXT, PK | Created by your system |
| `conversation_id` | TEXT | |
| `account_id` | TEXT | |
| `queue` | TEXT | For example billing, technical, security |
| `priority` | TEXT | low, normal, high or urgent |
| `created_at` | TEXT | ISO timestamp |
| `bundle_json` | TEXT | The handoff bundle (Annex D), PII redacted |

### Required tools

Implement at least these as deterministic tools over the tables above:
`lookup_account`, `get_usage`, `get_plan_limits`, `get_invoices`,
`check_refund_eligibility`, `check_platform_status`, `send_password_reset`
(mocked; never returns a token or link) and `create_handoff`.

> **Reserved for judges:** account IDs `A9000` to `A9999`, invoice IDs
> starting `INV-J`, and source IDs starting `JD-`. Do not use them in your own
> data.

## Annex D: Escalated response and handoff bundle

```json
{
  "trace_id": "e0a971c2",
  "answer_type": "escalated",
  "answer": "I'm sorry about the duplicate charge. I've passed this to our billing team with the details below. You will hear back within one business day. I can't issue refunds myself.",
  "handoff_id": "H-0042",
  "handoff": {
    "queue": "billing", "priority": "high",
    "intent": "billing_dispute", "urgency": "high", "sentiment": "angry",
    "escalation_reasons": ["billing_dispute", "explicit_human_request", "repeated_contact"],
    "customer_summary": "Customer reports being charged twice on 1 Oct.",
    "evidence": [
      {"tool": "get_invoices", "output": [
        {"invoice_id": "INV-6001", "amount": 49.0, "charged_on": "2026-10-01"},
        {"invoice_id": "INV-6002", "amount": 49.0, "charged_on": "2026-10-01"}]},
      {"source_id": "KB-BIL-003", "section": "Duplicate charges"}
    ],
    "attempted_answer": "Explained duplicate-charge policy; refund needs approval.",
    "unresolved_questions": ["Approve refund of INV-6002?"],
    "pii_redacted": true
  }
}
```

## Annex E: Synthetic data card template

| Field | What to write |
|---|---|
| Purpose | What the data is for and what it must exercise |
| Generator | Model name and version, temperature, number of calls |
| Prompts | Link to the verbatim prompts in the repo |
| Schema enforcement | How you forced valid structure (JSON schema, Pydantic, retries) |
| Row counts and distributions | Accounts per plan and status; usage and invoice distributions |
| Edge cases included | Which edge cases, and the account IDs that carry them |
| Validation results | Checks run, violations found, and how you fixed them |
| What the LLM got wrong | Errors you caught in generated data and how |
| Known limitations | Ways the data is unrealistic or incomplete |

## Annex F: Starter prompt for the knowledge base

"Use this as a starting point. It does **not** yet satisfy Section 4.1 (for
example, it has no product versions, deprecations, outdated tickets or policy
articles). Improving it is part of what we assess."

```text
Generate a customer support knowledge base for a fictional SaaS product
called 'CloudFlow' (workflow automation tool). Produce:

1. 30 help-center articles as markdown files covering:
   - Getting started (5 articles)
   - Account & billing (5 articles)
   - API & integrations (8 articles)
   - Troubleshooting (8 articles)
   - Advanced features (4 articles)

2. 25 resolved support tickets as JSON with:
   id, customer_question, intent (how_to/bug/billing/account/complaint),
   resolution, tags, resolved_at

Make at least 3 tickets be angry complaints requiring human escalation.
Output realistic, specific content with version numbers and error codes.
```
