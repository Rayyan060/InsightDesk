# Synthetic Customer-Account Data

Synthetic data for CloudFlow accounts, usage, invoices and platform status, in
the fixed Annex C schema (guide Section 4.2). The one-page data card is
[data_card.md](data_card.md), and the schema is in
[database_schema.md](database_schema.md).

## What is where

| Path | Contents | Origin |
|---|---|---|
| `data/reference/plan_limits.csv` | 4 plans | Hand-authored. Values are defined by policy article KB-POL-002 (Phase 3) |
| `data/reference/policy_registry.csv` | 23 policy rules | Hand-authored from Annex A. Each rule cites a `KB-POL-*` article and section |
| `data/synthetic/accounts.csv`, `usage.csv`, `invoices.csv`, `platform_status.csv` | The dataset of record | LLM run with seeded fallback (see [Provenance](#provenance-of-the-committed-dataset)) |
| `data/synthetic/edge_cases.csv` | Which account carries which edge case | Generated |
| `data/synthetic/validation_report.md` / `.json` | Output of the validation pipeline | Generated |
| `data/synthetic/generation_manifest.json` | Generator, seed, reference date, counts, LLM statistics | Generated |
| `data/synthetic/prompts/*_v1.md` | **Verbatim** LLM prompts | Hand-written |

Synthetic customer data is kept apart from application configuration (`.env`)
and from the hand-authored reference data.

## Provenance of the committed dataset

The committed CSVs come from a **real LLM run**:

* **Run:** `generator: llm`, model **qwen2.5:7b**, temperature **0.2**, seed
  **20261006**, reference date **2026-10-06**, prompt **v1**, at
  2026-10-06T09:19:08Z.
* **Cost:** **105 LLM calls**, 135,036 prompt tokens and 48,920 completion
  tokens.
* **Acceptance:** of 37 targets (36 accounts + platform status), **5 were
  accepted** (2 on the first try, 3 after retry). **32 accounts fell back to
  the deterministic seeded filler** after failing validation 3 times.
* **What came from where:**

  | Records | Source |
  |---|---|
  | A1001, A1002, A1003, A1015 (12 usage rows, 19 invoices) and the 6 platform-status rows | LLM-generated |
  | All other 32 accounts | Seeded |
  | Every ID, date, amount, status and pinned boundary value | Fixed by the blueprint and verified, in both cases |

* **Why the fallbacks:** all 97 conformance rejections included a duplicate
  `owner_email`.
* **Known LLM mistakes in the accepted records:**
  * generic emails (`john.doe@`, `jane.doe@`, `jane.smith@example.com`);
  * a duplicate company name, "FictionalTech", on A1002 and A1003.

  Full details are in the [data card](data_card.md#customer-accounts).

## Method

**Code owns the invariants; the generator supplies the realism.**

1. **Scenario plan** (`backend/app/synthetic/scenarios.py`): 24 named scenarios
   (A1001–A1024) cover every required edge case, followed by 12 seeded baseline
   accounts (A1025–A1036).
2. **Blueprints** (`generator.build_blueprints`): per account, the exact
   invariants are fixed in code:
   * account ID, plan, status, product version and creation date;
   * invoice IDs, charge dates, amounts and statuses;
   * the pinned usage values for boundary cases.

   Refund-window boundaries are computed from the **policy registry** in effect
   on the reference date. With REFUND-WINDOW-01 (14 days) that is `ref − 14` and
   `ref − 15`, so the data and the policy can't drift apart.
3. **Filler**, which supplies company names, owner emails, failure reasons and
   all non-pinned usage values:
   * `seeded` (default): one `random.Random(seed)`, so the same inputs give
     byte-identical CSVs (tested);
   * `llm`: Ollama with the verbatim prompts in `data/synthetic/prompts/`.
     Values are marked **FIXED** (copy exactly) or **FREE** (choose within
     bounds). The reply must match the JSON schema of `AccountBundle`
     (Ollama structured output), then pass the Annex C row models and a
     **conformance check** against the blueprint. Failures are retried up to
     `--max-attempts` times, with the exact problems fed back. After that the
     account falls back to the seeded filler (recorded in the report), or the
     run aborts with `--llm-fallback fail`.
4. **Validation**: schema, referential, business and reserved-ID checks, plus
   **edge-case verification from the data** (see below).
5. **Export**: deterministic CSVs (Annex C column order, sorted by primary key).
   Existing files are never overwritten without `--force`.
6. **Import check**: the CSVs are loaded into a *throwaway* SQLite database
   with the real loader, and the row counts are compared. The application
   database is never touched.
7. **Report**: `validation_report.md` / `.json`.

Why split the work this way? Edge cases have to be exact, and Section 4.2's
boundaries ("exactly at", "one unit over", "last day", "one day after") are
precisely where LLM arithmetic fails. R7 already forbids LLM arithmetic for
account facts. So the LLM contributes realistic content under a schema, and
the code guarantees the boundaries and verifies everything.

## Parameters

| Parameter | Value |
|---|---|
| Seed | `20261006` |
| Reference date | `2026-10-06` (the event date). Relative edge cases hold for `as_of_date = 2026-10-06` |
| Accounts | 36 (A1001–A1036). Hard limit: IDs can never reach A9000 |
| Invoice IDs | `INV-6001` upwards (never `INV-J…`) |
| Usage periods | 2026-08, 2026-09, 2026-10 (current, partial month) |
| Product versions | 4.3 (current), 4.2, 4.1, 4.0, 3.9, 3.8 (legacy 3.x) |
| Currencies | USD; INR at the fixed rate 83 INR = 1 USD |
| LLM defaults | `OLLAMA_MODEL`, temperature 0.2, seed = generator seed (+ offsets), 3 attempts |

## Distributions (dataset of record)

| | Free | Pro | Business | Enterprise | Total |
|---|---|---|---|---|---|
| active | 7 | 11 | 6 | 3 | 27 |
| past_due | – | 1 | – | 2 | 3 |
| suspended | – | – | 1 | 1 | 2 |
| cancelled | 2 | 1 | 1 | – | 4 |
| **Total** | 9 | 13 | 8 | 6 | **36** |

* **Product versions:** 4.3 × 22, 4.2 × 6, 4.1 × 3, 4.0 × 2, 3.9 × 2, 3.8 × 1.
* **Invoices (89):** paid 81, failed 7, refunded 1. USD 87, INR 2.
* **Invoices per account:** 0 → 9 accounts (every Free account, which is never
  charged), 2 → 13, 3 → 2, 4 → 4, 5 → 7, 6 → 1.
* **Usage (96 rows):** 32 per period. Cancelled accounts have no rows after
  cancellation.
* **Platform status (6):**
  * operational: api, auth, billing, workflow-engine;
  * degraded: connectors (`INC-2026-1004`);
  * outage: webhooks (`INC-2026-1005`).

## Edge cases (verified from the data)

Each case is a predicate evaluated over the generated records
(`backend/app/synthetic/edge_cases.py`). It passes only if the assigned
account satisfies it **and** the data contains at least one such account.

| Edge case | Account | How it shows in the data |
|---|---|---|
| Active, within quota | A1001 | Pro; every current metric < 80% of its limit |
| Approaching quota | A1002 | Business; 135,000 / 150,000 workflow runs (90%) |
| Usage **exactly at** a limit | A1003 | Pro; 20,000 / 20,000 runs |
| Usage **one unit over** | A1004 | Pro; 20,001 / 20,000 runs |
| API rate exactly at limit | A1005 | Business; peak 3,000 / 3,000 per minute |
| API rate one over (429s) | A1006 | Pro; peak 601 / 600 per minute |
| Seats at limit | A1007 | Free; 2 / 2 seats |
| Failed payment | A1008 | Pro, past_due; latest invoice failed with a failure reason |
| Suspended account | A1009 | Business; last two invoices failed |
| Duplicate charge | A1010 | Pro; INV-6037 and INV-6038, both 49.0 USD on 2026-10-01 (mirrors Annex D) |
| Charge on the **last day** of the refund window | A1011 | Pro; INV-6040 charged 2026-09-22 = ref − 14 days (REFUND-WINDOW-01: eligible) |
| Charge **one day after** the window | A1012 | Business; INV-6042 charged 2026-09-21 = ref − 15 days (not eligible) |
| Enterprise window (scope_plans) | A1013 | Enterprise; charged 20 days ago, inside the 30-day REFUND-WINDOW-02 only |
| No invoices | A1014 | Free account |
| Multiple invoices | A1015 | Enterprise; 6 monthly invoices |
| Recently upgraded | A1016 | Pro invoices at 49.0, then Business at 299.0 on 2026-10-02 |
| Older product version | A1017 | Pro on 3.9 (also A1018 on 3.8) |
| Cancelled accounts | A1019, A1020 | Paid plan (invoices stop 3 months back) and Free |
| Past-due Enterprise | A1021 | Expired card |
| Refunded invoice | A1022 | INV-6065 refunded |
| INR billing | A1023 | 4,067.0 INR per month |
| Suspended Enterprise | A1024 | Two failed invoices |

Coverage checks also pass: all 4 plans, all 4 statuses, all 3 invoice statuses,
6 product versions, ≥ 30 accounts.

## Validation results

The latest run is in [`data/synthetic/validation_report.md`](../data/synthetic/validation_report.md):

* **0 errors, 0 warnings.** Since Phase 3, the policy rules' `source_id`s are
  verified against the Source Register.
* **20/20** edge-case and coverage checks pass.
* CSV and SQLite row counts match.

Rules checked:

| Code | Rule |
|---|---|
| `schema` | Every Annex C row rule: formats, enumerations, `amount > 0`, last-4 only, example.com, empty `failure_reason` unless failed, empty `incident_id` if operational |
| `duplicate_key` / `foreign_key` | Unique PKs; `usage`/`invoices` reference real accounts |
| `status_vs_invoices` | past_due → latest invoice failed; suspended → latest invoice failed; active → latest invoice not failed |
| `status_vs_usage` | cancelled → no workflow runs in the reference period |
| `free_plan_billed` | Free accounts aren't charged |
| `charge_before_creation`, `usage_before_creation`, `future_date` | Date consistency |
| `reserved_id` | No A9000–A9999, `INV-J…` or `JD-…` in our data |
| `policy_value`, `policy_ambiguous` | Numeric thresholds; no two rules with the same parameter, plan and effective date |
| `edge_case_missing` | Any required edge case or coverage check failing |

Problems the validator caught during development:

* A precedence bug in cancelled-account charge dates. It was found by the
  conformance self-check.
* The `refunded_invoice` scenario silently produced no refunded invoice,
  because its random history had only 2 invoices. Fixed by pinning 4 invoices
  and adding the `coverage_all_invoice_statuses` check.

## Commands

```bash
# Generate (refuses to overwrite existing CSVs without --force)
python scripts/generate_data.py                          # seeded, reproducible
python scripts/generate_data.py --generator llm --force  # Ollama (OLLAMA_BASE_URL / OLLAMA_MODEL)
python scripts/generate_data.py --out /tmp/try --seed 7  # experiment elsewhere

# Validate (writes data/synthetic/validation_report.*)
python scripts/validate_data.py
python scripts/validate_data.py --mode judge --dir test_accounts/   # judge data: business rules are warnings

# Database
python scripts/init_db.py --with-synthetic               # schema + reference + our accounts
python scripts/load_accounts.py --dir test_accounts/     # judge loader (guide Section 4.2)
python scripts/load_accounts.py --dir test_accounts/ --dry-run
python scripts/load_accounts.py --dir test_accounts/ --on-conflict overwrite --allow-overwrite

# Inspect / export (emails masked)
python scripts/inspect_data.py
python scripts/inspect_data.py --account A1010
python scripts/inspect_data.py --export exports/
```

Inside Docker: `docker compose exec backend python -m app.cli.load_accounts --dir /app/data/test_accounts`.

## Limitations

* **Only 4 of 36 accounts are LLM-filled.** The rest fell back to seeded data
  (see [Provenance](#provenance-of-the-committed-dataset)). LLM free-text fields
  (company name, email) can't be byte-reproduced. They are protected by schema
  validation, while fallback rows and all invariants are verified exactly by
  the reproducibility tests.
* **Duplicate company names.** "FictionalTech" (A1002 and A1003, LLM),
  "Lumenary Health" (A1005, A1030) and "Sablewood Studios" (A1019, A1036);
  the last two are seeded fallbacks with independent RNG streams. Annex C
  doesn't require unique names, so the validator doesn't reject them.
* Usage is monthly aggregates only, with no per-day series. The current period
  is partial (6 days), so most current-month run counts are low.
* One payment card per account, flat monthly prices and a fixed INR rate. No
  taxes, discounts, proration or annual billing. Upgrades are visible only
  through invoice amounts, since Annex C has no plan-history table.
* Relative edge cases hold for the reference date 2026-10-06. For another date,
  regenerate with `--reference-date`; the refund-window cases then follow the
  policy rule in effect, for example 7 days from 2026-11-01.
* Policy `source_id`s point at `KB-POL-001`–`006`, written in Phase 3. The
  knowledge validator checks each cited section and value.
