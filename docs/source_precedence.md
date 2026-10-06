# Source Precedence (Annex A)

How InsightDesk decides which knowledge it may use, and which wins when
sources disagree. Phase 3 implements the **metadata and the deterministic
applicability filter** (`backend/app/knowledge/precedence.py`). Phase 4
implements retrieval ranking on top of it.

## Authority levels (Annex A.1)

| Level | Source | `doc_type` | Notes |
|---|---|---|---|
| 1 (highest) | Current help-center and policy articles | `article`, `policy` | Must match the customer's product version |
| 2 | Release notes and deprecation notices | `release_note` | Dates matter; a deprecation may not have taken effect yet |
| 3 | Live tool results (platform status, account data) | — (never stored) | Authoritative for current state; always cite the tool |
| 4 | Resolved tickets | `ticket` | Historical evidence only; may be outdated |
| 5 (untrusted) | Customer-provided text, community posts | `community` | Never authoritative |

`authority_level` in the Source Register must equal the level for its
`doc_type`; the validator rejects any mismatch. No stored document can claim
level 3.

## Resolution order (Annex A.2)

| Step | Rule | Implementation |
|---|---|---|
| 1. Applicability | Use only sources whose `product_versions` cover the customer's version and that are in effect on `as_of_date` | `applicability()`: `version_not_covered`, `not_yet_effective` (`effective_from > as_of`), `deprecated` (`deprecated_on ≤ as_of`). A future `deprecated_on` is a **notice** (`deprecation_upcoming:<date>`), not an exclusion: "mention upcoming deprecations" |
| 2. Explicit supersession and deprecation | A newer source that explicitly replaces earlier guidance wins from its effective date | `superseded_by:<id>` when the superseding source is in effect on `as_of` (its `effective_from`, else `last_updated`) **and** covers the customer's version |
| 3. Authority | Higher authority wins regardless of date; a ticket never contradicts documentation | `authority_level` on every section record. **Ranking: Phase 4** |
| 4. Recency | Same authority: the more recently updated source wins | `last_updated` on every section record. **Ranking: Phase 4** |
| 5. Unresolved | Escalate with both sources in the handoff bundle | Policy KB-POL-003 "When we hand off". **Escalation: Phase 5** |

Conflicts found in steps 3–5 are recorded in the audit trail and in the
response's `conflicts_detected` (R6).

## Worked examples (data in this repository)

| Customer | Question | Applicable sources (step 1–2) | Winner (step 3–4) | Conflict to record |
|---|---|---|---|---|
| 3.9, 2026-10-06 | "Salesforce step fails with CF-503" | KB-TRB-002 (1), TKT-2025-0342 (4), COM-0001 (5) | KB-TRB-002 "Fix in 3.x" | TKT-2025-0342 / COM-0001 say "disable SSL", contradicted |
| 4.3, 2026-10-06 | Same | KB-TRB-002 (1), TKT-2025-0398 (4) | KB-TRB-002 "Fix in 4.x" (Reconnect) | TKT-2025-0398 "delete and recreate" |
| 4.3, 2026-10-06 | "How do I rotate my API token?" | KB-API-014 (KB-API-009 is `superseded_by:KB-API-014`) | KB-API-014 "Rotating in 4.2 and later" | — |
| 4.1, 2026-10-06 | Same | KB-API-014, TKT-2025-0520 | KB-API-014 "Rotating in 4.0 and 4.1" | none: the ticket agrees for 4.0–4.1 |
| 3.9, 2026-10-06 | "Run a workflow every night" | KB-ADV-003 and TKT-2025-0414 are `deprecated`; KB-ADV-004 covers 4.1+ only | none for 3.9 | Not covered for 3.x: explain that an upgrade is needed, or `not_found` with a handoff |
| 3.9, 2026-10-06 | "API key questions" | KB-API-002 with notice `deprecation_upcoming:2026-12-01`, RN-2026-09 | KB-API-002 | Mention the 2026-12-01 deadline |
| Pro, 2026-10-06 | "Refund a 30-day-old charge" | KB-POL-001 (1), TKT-2025-0472 (4) | KB-POL-001 (14 days) | TKT-2025-0472 was a human exception, never precedent |
| Any | "Raise my rate limit" | KB-API-003 + KB-POL-002 (1), TKT-2025-0450 (4), COM-0002 (5) | Policy: no case-by-case raises | TKT-2025-0450 / COM-0002 |
| 4.3 | "Export run history" | KB-ADV-007 only (KB-ADV-005 is 3.x, KB-ADV-006 is 4.0–4.1) | KB-ADV-007 "Steps" | — |

Try any of them with
`python scripts/inspect_knowledge.py --version <v> --as-of <date>`.

## What Phase 4 receives

Each section record from `section_records()` carries:

* `chunk_id`, `source_id`, `doc_type`, `title`, `section`, `text`;
* `authority_level`;
* `product_versions`, `last_updated`, `effective_from`, `deprecated_on`;
* `supersedes`, `superseded_by`, `synthetic`.

That covers R3 citations (source ID, section, product versions, last-updated
date) and every input the filter and ranking need. No second metadata
standard exists: all of these come from the Annex B register.

## Knowledge is data, not instructions

Knowledge documents, ticket text and customer messages are **data** (R10).
Whatever a retrieved document says, it **cannot**:

| Cannot | Because |
|---|---|
| Modify policies or escalation thresholds | Policy values come only from the `policy_registry` table, loaded from a reviewed CSV by the operator CLI. `PolicyRegistryRepository` is read-only, and nothing in `app/knowledge` writes policy (tested) |
| Modify the system prompt or behaviour | Phase 4 must insert document text only through `as_untrusted_data()`. That is a delimited block labelled with source ID and authority, which the content cannot close (delimiter look-alikes are neutralised; tested) |
| Reveal secrets | Documents contain no secrets. Tools never return tokens or reset links (`PasswordResetResult` forbids them) |
| Change account identity | The account comes only from the `X-Account-Id` header (R8). Tool requests reject an `account_id` argument |
| Execute tools | Tools are called only through `invoke_tool` by the agent's own logic. Documents are never parsed for commands, and nothing in `app/knowledge` imports the tool layer (tested) |

`scan_for_instructions()` flags injection attempts (the three fixtures:
COM-0001, COM-0002, TKT-2026-0240), so they can be logged and down-weighted.
It is a signal, not the defence: the defence is that no code path lets
document content act.
