# Database Schema (Annex C)

The SQLite schema implements **Annex C, "Fixed data schema"**, of the participant
guide exactly. Every required table and column exists with the documented name
and SQL type. Nothing has been renamed, removed or retyped, and no columns have
been added. Judges load their own test accounts into this schema, so it is
treated as a fixed external contract.

* Transcription of the guide: [reference/guide_extract.md](reference/guide_extract.md#annex-c-fixed-data-schema-sqlite)
* ORM models: `backend/app/database/models.py`
* Independent transcription used for verification: `backend/app/database/annex_c.py`
  (`verify_schema()` compares a live database with it, used by `init_db`,
  `/health` and the tests)

## Tables

PK = primary key, FK = foreign key. "Rule" is the Annex C rule; "Enforced by"
says where we enforce it (**DB** = SQLite CHECK, **Row** = row validation in
`row_schemas.py`).

### `accounts`

| Column | Type | Rule (Annex C) | Enforced by |
|---|---|---|---|
| `account_id` | TEXT, PK | `A` followed by 4 digits | DB + Row |
| `company_name` | TEXT | Synthetic | Row (non-empty) |
| `owner_email` | TEXT | Synthetic, `@example.com` domains only; treat as PII | DB + Row |
| `plan` | TEXT | Free, Pro, Business or Enterprise | DB + Row |
| `status` | TEXT | active, past_due, suspended or cancelled | DB + Row |
| `product_version` | TEXT | e.g. 4.3 | Row (`N.N` or `N.N.N`) |
| `created_at` | TEXT | YYYY-MM-DD | DB (format) + Row (valid date) |

### `plan_limits`

| Column | Type | Rule | Enforced by |
|---|---|---|---|
| `plan` | TEXT, PK | One row per plan | DB + Row |
| `api_rate_limit_per_min` | INTEGER | | DB + Row (≥ 0) |
| `monthly_workflow_runs` | INTEGER | | DB + Row (≥ 0) |
| `seats` | INTEGER | | DB + Row (≥ 0) |
| `support_tier` | TEXT | e.g. standard or priority | Row |
| `monthly_price` | REAL | | DB + Row (≥ 0) |

### `usage`

| Column | Type | Rule | Enforced by |
|---|---|---|---|
| `account_id` | TEXT, FK → `accounts.account_id` | PK with `period` | DB (FK) + loader |
| `period` | TEXT, PK | YYYY-MM | DB + Row |
| `workflow_runs` | INTEGER | Runs so far in the period | DB + Row (≥ 0) |
| `api_calls_peak_per_min` | INTEGER | Highest per-minute rate in the period | DB + Row (≥ 0) |
| `seats_used` | INTEGER | | DB + Row (≥ 0) |

### `invoices`

| Column | Type | Rule | Enforced by |
|---|---|---|---|
| `invoice_id` | TEXT, PK | | Row (1–64 chars `[A-Za-z0-9_-]`) |
| `account_id` | TEXT, FK → `accounts.account_id` | | DB (FK) + loader |
| `amount` | REAL | > 0 | DB + Row |
| `currency` | TEXT | e.g. USD or INR | Row (3-letter code) |
| `charged_on` | TEXT | YYYY-MM-DD | DB + Row |
| `status` | TEXT | paid, failed or refunded | DB + Row |
| `failure_reason` | TEXT | Empty unless failed | DB + Row |
| `card_last4` | TEXT | Last four digits only; never full card numbers | DB + Row |

### `platform_status`

| Column | Type | Rule | Enforced by |
|---|---|---|---|
| `component` | TEXT, PK | e.g. api, workflow-engine, connectors, billing | Row |
| `status` | TEXT | operational, degraded or outage | DB + Row |
| `incident_id` | TEXT | Empty if operational | DB + Row |
| `updated_at` | TEXT | ISO timestamp | Row |

### `policy_registry`

| Column | Type | Rule | Enforced by |
|---|---|---|---|
| `rule_id` | TEXT, PK | e.g. REFUND-WINDOW-01 | Row |
| `description` | TEXT | Plain-language description | Row |
| `parameter` | TEXT | e.g. `refund_window_days`, `critic_min_groundedness` | Row (snake_case) |
| `operator` | TEXT | `<=`, `>=` and so on | Row (`<`, `<=`, `>`, `>=`, `==`, `!=`, `in`, `not_in`) |
| `value` | TEXT | | Row; numeric for comparison operators |
| `scope_plans` | TEXT | ALL or a list of plans | Row (`ALL` or `;`-separated plans) |
| `effective_from` | TEXT | YYYY-MM-DD | DB + Row |
| `source_id` | TEXT | Policy article in the Source Register | Row; existence checked once the register exists (Phase 3) |
| `source_section` | TEXT | | |

### `handoffs`

| Column | Type | Rule | Enforced by |
|---|---|---|---|
| `handoff_id` | TEXT, PK | Created by our system | Row |
| `conversation_id` | TEXT | | Row |
| `account_id` | TEXT | (not an FK in Annex C) | Row (A + 4 digits) |
| `queue` | TEXT | e.g. billing, technical, security | Row |
| `priority` | TEXT | low, normal, high or urgent | DB + Row |
| `created_at` | TEXT | ISO timestamp | Row |
| `bundle_json` | TEXT | Annex D bundle, PII redacted | DB (`json_valid`) + Row (JSON object) |

## Design decisions

| Decision | Why |
|---|---|
| Dates and timestamps stay `TEXT` | Annex C specifies TEXT. ISO strings sort correctly and match the judges' CSVs byte for byte |
| Only the FKs Annex C marks (`usage.account_id`, `invoices.account_id`) | Adding FKs Annex C doesn't specify (for example `accounts.plan` → `plan_limits`, or `handoffs.account_id`) could reject judge data. Unknown plans are reported by the validator instead |
| CHECK constraints encode only explicit Annex C rules | Defence in depth for PII rules (last-4 only, example.com) and enumerations, without imposing our own business interpretation |
| Business consistency ("statuses consistent with invoices") is validated, not constrained | Errors for our own data. **Warnings** for judge data, which must never be blocked by our interpretation |
| Reserved IDs (A9000–A9999, INV-J…, JD-…) allowed by the DB and the loader | Judges load exactly these. Only our generator and validator forbid them for our own data |
| `PRAGMA foreign_keys=ON` on every connection | SQLite disables FKs by default |
| Indexes: `accounts(plan)`, `accounts(status)`, `usage(period)`, `invoices(account_id, charged_on)`, `policy_registry(parameter)`, `handoffs(account_id)`, `handoffs(conversation_id)` | Tool query paths (an account's invoices newest first, rules by parameter). Additive, so the contract is unchanged |
| Enumerations matched case-insensitively on load, stored canonically | `pro` / `PAID` in a judge CSV is clearly intended. Stored as `Pro` / `paid` so the CHECK constraints and tools see one spelling |

## Initialisation (idempotent)

```bash
python scripts/init_db.py                    # schema + plan_limits + policy_registry
python scripts/init_db.py --with-synthetic   # + our 36 synthetic accounts
```

* Only `CREATE TABLE` for missing tables: never `DROP`, `DELETE` or `ALTER`.
* Reference rows load with the **skip** policy. Identical rows are left
  unchanged, and rows an operator edited in the database are kept, not
  overwritten.
* The API runs the same initialisation at startup when `SEED_REFERENCE_DATA=true`
  (the default).

## Access patterns

* **`AccountScopedRepository(session, AccountContext)`**: all account-owned data.
  No method takes an account ID. Every query filters by the header account
  through bound parameters, and another account's invoice looks exactly like a
  missing one.
* **`ReferenceRepository`**: plan limits and platform status.
* **`PolicyRegistryRepository`**: **read-only**, with no mutating methods. Rules
  change only through reviewed CSVs and the operator CLI, never at request
  time and never by the LLM.
* **`HandoffRepository`**: the only write path, used by `create_handoff` (Phase 5).

## Import and export

See [synthetic_data.md](synthetic_data.md#commands) for every command. The
loader (`scripts/load_accounts.py`):

| Property | Behaviour |
|---|---|
| Header matching | By name; case-insensitive and whitespace-trimmed; any column order. Extra columns are warned about and ignored |
| Required columns | Missing ones reject the file |
| Row validation | Annex C row models. Errors report table, CSV row number and column, never the value |
| Foreign keys | `usage`/`invoices` must reference an existing or co-imported account |
| Transactions | One transaction per run. Any error rolls back everything (`--skip-invalid` commits valid rows and reports the rest) |
| Duplicates within a file | Rejected |
| Re-running the same import | No-op: rows are reported `unchanged` |
| Different existing record | `--on-conflict error` (default) or `skip`. `overwrite` also needs `--allow-overwrite` |
| Malformed files | Non-UTF-8, NUL bytes, broken quoting, empty, over 20 MB or over 200k rows are reported, not crashed on |
| File names | `<table>.csv` (e.g. `accounts.csv`). Other CSVs are warned about and ignored |
