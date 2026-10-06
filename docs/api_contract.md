# InsightDesk API Contract

Interactive docs: `http://localhost:8000/docs` (OpenAPI JSON at `/openapi.json`).

> **Source of truth:** participant guide Section 6 (mandatory API contract),
> Section 6.1 (response format), Section 6.2 (answer types) and Annex D
> (escalated response). Transcription: [reference/guide_extract.md](reference/guide_extract.md).
> The Pydantic schemas in `backend/app/schemas/` are tested against the
> guide's own example JSON (`tests/test_schemas.py`).

## Conventions

| Item | Convention |
|---|---|
| Customer identity | `X-Account-Id` header, **only** (R8). 1–64 chars `[A-Za-z0-9_-]`, e.g. `A1001`. Not authentication. A malformed header gets **400**; a well-formed unknown account becomes a tool-level `account_not_found` (Phase 5) |
| Trace ID | Every response has an `X-Trace-Id` header. A client may send its own `X-Trace-Id` (8–64 chars `[A-Za-z0-9-]`) |
| Body limit | `MAX_REQUEST_BYTES` (default 65,536). Larger bodies get **413** |
| Dates | `YYYY-MM-DD` |
| Errors | All non-2xx responses use the envelope below |

### Error envelope

```json
{"error": {"code": "validation_error", "message": "Request validation failed.",
           "details": [{"loc": ["body", "message"], "msg": "Field required", "type": "missing"}]},
 "trace_id": "3f2a9c1b0d4e5f60718293a4b5c6d7e8"}
```

`details` never includes the rejected value. Codes: `invalid_account_context`
(400), `not_found` (404), `payload_too_large` (413), `validation_error` (422),
`internal_error` (500), `not_implemented` (501), `service_unavailable` (503).

## Endpoints (Section 6)

| Endpoint | Purpose | Status |
|---|---|---|
| `POST /support` | Handle a customer message | Request validated; **501 until Phase 4** |
| `POST /ingest` | Add an article or ticket while running (multipart: Markdown article or JSON ticket + Annex B metadata) | 501 until Phase 3 |
| `GET /health` | Status of API, vector store, SQLite and LLM | **Implemented.** SQLite also reports Annex C conformance and row counts |
| `GET /conversations/{id}` | Messages, routes taken and responses | 501 until Phase 4 |
| `GET /handoffs/{id}` | The full bundle created at escalation (`HandoffRecord`) | 501 until Phase 5 |
| `GET /audit/{trace_id}` | Full audit record for one response | 501 until Phase 5 |
| `GET /sources` | Source Register (all ingested articles and tickets with metadata) | 501 until Phase 3 |
| Test-data loader | Loads CSVs in the Annex C schema | **Implemented:** `python scripts/load_accounts.py --dir test_accounts/` |
| `GET /health/live` | Liveness for the Docker healthcheck (addition) | Implemented |
| `GET /handoffs` | Handoff list (addition) | 501 until Phase 5 |

## `POST /support`

### Request

| Field | Type | Required | Notes |
|---|---|---|---|
| header `X-Account-Id` | string | for account questions | The only source of the customer's account |
| `message` | string, 1–4000 chars (trimmed) | **yes** | Never logged |
| `conversation_id` | string `[A-Za-z0-9_-]{1,64}` | no | e.g. `C-0192` |
| `channel` | string `[a-z][a-z0-9_-]{0,31}` | no | e.g. `web`, `email`, `chat` |
| `product_version` | string `N`, `N.N` or `N.N.N` | no | Customer-stated version |
| `as_of_date` | `YYYY-MM-DD` | no | Defaults to today (applied by the server) |

Unknown fields are ignored. A body `account_id`, in particular, has no effect (R8).

### Response (Section 6.1)

```json
{
  "trace_id": "b81e0c44", "conversation_id": "C-0192", "answer_type": "answered",
  "answer": "In CloudFlow 4.3, open Workflows, select the workflow, then ...",
  "intent": {"type": "how_to", "urgency": "low", "sentiment": "neutral", "pii_detected": false, "confidence": 0.92},
  "citations": [{"source_id": "KB-ADV-007", "doc_type": "article", "section": "Steps",
                 "product_versions": "4.2+", "last_updated": "2026-09-10"}],
  "tools_invoked": [{"tool": "lookup_account", "output": {"plan": "Pro", "status": "active", "product_version": "4.3"}}],
  "critic": {"groundedness": 0.94, "coverage": "complete", "pii_risk": "none", "policy_risk": "none",
             "decision": "answer", "revisions": 0},
  "conflicts_detected": [], "handoff_id": null, "as_of_date": "2026-10-06"
}
```

| Field | Schema | Constraints |
|---|---|---|
| `answer_type` | `AnswerType` | `answered` · `clarification_needed` · `escalated` · `not_found` · `refused` · `out_of_scope` (Section 6.2) |
| `intent` | `IntentInfo` | `type` ∈ R1 intents (`how_to`, `troubleshooting`, `account`, `billing`, `complaint`, `security`, `out_of_scope`); `urgency` ∈ low/normal/high/urgent; `sentiment` ∈ positive/neutral/negative/angry; `confidence` 0–1; optional `product_version` (omitted when unknown) |
| `citations[]` | `Citation` | `doc_type` ∈ Annex B types (article, policy, release_note, ticket, community) |
| `tools_invoked[]` | `ToolInvocation` | `{"tool", "output"}` on success, or `{"tool", "error"}` on failure, never both |
| `critic` | `CriticReport` | `decision` ∈ answer/revise/escalate; `revisions` ≤ 1 (R4) |
| `handoff_id`, `handoff` | `HandoffBundle` (Annex D) | Both are required when `escalated`, and absent otherwise. The bundle must have `pii_redacted: true` |
| `conflicts_detected[]` | `ConflictRecord` | `description`, `source_ids`, `resolution`. The guide's example shows only `[]`, so the item shape is our design |

### Escalated response (Annex D)

`answer_type: "escalated"`, plus `handoff_id` (e.g. `H-0042`) and `handoff`:
`queue`, `priority`, `intent`, `urgency`, `sentiment`, `escalation_reasons[]`,
`customer_summary`, `evidence[]` (`{"tool","output"}` or
`{"source_id","section"}`), `attempted_answer`, `unresolved_questions[]`,
`pii_redacted`.

## Tools (Annex C "Required tools")

Typed contracts live in `backend/app/schemas/tools.py`, and the dispatcher in
`backend/app/tools/registry.py`. Business logic arrives in Phase 5; until then
every call returns a `not_implemented` error and never data.

| Tool | Request | Response | Account-scoped | Reads / writes |
|---|---|---|---|---|
| `lookup_account` | — | `AccountSummary` (email **masked**) | yes | accounts |
| `get_usage` | `period?` (YYYY-MM) | `UsageReport` (per metric: used, limit, utilization, state) | yes | usage, accounts, plan_limits, policy_registry |
| `get_plan_limits` | `plan?` | `PlanLimitsResult` | yes | plan_limits, accounts |
| `get_invoices` | `limit` (1–50), `status?`, `since?` | `InvoiceList` | yes | invoices |
| `check_refund_eligibility` | `invoice_id?` | `RefundEligibilityResult` (`requires_human_approval` is always true) | yes | invoices, accounts, policy_registry |
| `check_platform_status` | `component?` | `PlatformStatusResult` | no | platform_status |
| `send_password_reset` | — (always the owner email on file) | `PasswordResetResult`: no token or link fields; text is validated against links and tokens | yes | accounts |
| `create_handoff` | `conversation_id?`, `queue`, `priority`, `bundle` | `HandoffCreated` | no (uses the header account if present) | writes **handoffs** |

Error codes: `account_context_required`, `account_not_found`, `not_found`,
`invalid_arguments` (including any `account_id` argument: request models
forbid unknown fields), `unknown_tool`, `data_unavailable`, `not_implemented`,
`internal_error`.

## Remaining design choices (not specified by the guide)

1. The item shape of `conflicts_detected` (the guide only shows `[]`).
2. The value sets of `urgency` and `sentiment`, inferred from the examples
   (`low`, `high`, `neutral`, `angry`).
3. Queue names beyond the Annex C examples (billing, technical, security):
   we add account, legal and general.
4. Validation errors return HTTP 422. A vague but valid message gets 200 with
   `clarification_needed` (Phase 4).
