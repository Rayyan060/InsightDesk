# Synthetic data validation report

**Result:** PASS  
**Generator:** llm (model qwen2.5:7b, temperature 0.2); seed 20261006; reference date 2026-10-06

## Pipeline steps

| Step | Result | Detail |
|---|---|---|
| generate | ok | llm generator, 36 accounts |
| validate_schema | ok | 0 schema errors |
| validate_business | ok | 0 errors; 20/20 edge-case and coverage checks passed |
| export_csv | ok | accounts.csv, invoices.csv, platform_status.csv, usage.csv |
| import_sqlite | ok | committed=True |
| verify_row_counts | ok | all match |
| write_report | ok | validation_report.md, validation_report.json |

## Issues (0 errors, 1 warning)

| Severity | Code | Table | Key | Column | Message |
|---|---|---|---|---|---|
| warning | policy_source_unverified | policy_registry |  | source_id | source_id of 23 rules not checked: no source register available yet (the policy articles are written with the knowledge base in Phase 3) |

## Edge cases and coverage (verified from the data)

| Check | Result | Manifest account | Satisfied by |
|---|---|---|---|
| active_within_quota | pass | A1001 | A1001, A1010, A1011, A1012, A1013, A1014, A1016, A1017 ... |
| approaching_quota | pass | A1002 | A1002, A1003, A1015 |
| workflow_runs_at_limit | pass | A1003 | A1003 |
| workflow_runs_one_over | pass | A1004 | A1004 |
| api_rate_at_limit | pass | A1005 | A1005 |
| api_rate_one_over | pass | A1006 | A1006 |
| failed_payment | pass | A1008 | A1008, A1021, A1027 |
| suspended_account | pass | A1009 | A1009, A1024 |
| duplicate_charge | pass | A1010 | A1010 |
| refund_last_day_of_window | pass | A1011 | A1011 |
| refund_one_day_after_window | pass | A1012 | A1006, A1012 |
| no_invoices | pass | A1014 | A1007, A1014, A1018, A1020, A1028, A1030, A1032, A1033 ... |
| multiple_invoices | pass | A1015 | A1001, A1002, A1003, A1004, A1006, A1008, A1009, A1010 ... |
| recently_upgraded | pass | A1016 | A1016 |
| older_product_version | pass | A1017 | A1017, A1018, A1025 |
| coverage_all_plans | pass |  | Business, Enterprise, Free, Pro |
| coverage_all_statuses | pass |  | active, cancelled, past_due, suspended |
| coverage_all_invoice_statuses | pass |  | failed, paid, refunded |
| coverage_multiple_versions | pass |  | 3.8, 3.9, 4.0, 4.1, 4.2, 4.3 |
| coverage_min_30_accounts | pass |  | 36 |

## Row counts (CSV vs SQLite import)

| Table | Expected | In database |
|---|---|---|
| accounts | 36 | 36 |
| usage | 96 | 96 |
| invoices | 89 | 89 |
| platform_status | 6 | 6 |
| plan_limits | 4 | 4 |
| policy_registry | 23 | 23 |

## Distributions

```json
{
  "accounts_by_plan_and_status": {
    "Pro": {
      "active": 11,
      "past_due": 1,
      "cancelled": 1
    },
    "Business": {
      "active": 6,
      "suspended": 1,
      "cancelled": 1
    },
    "Free": {
      "active": 7,
      "cancelled": 2
    },
    "Enterprise": {
      "active": 3,
      "past_due": 2,
      "suspended": 1
    }
  },
  "accounts_by_product_version": {
    "3.8": 1,
    "3.9": 2,
    "4.0": 2,
    "4.1": 3,
    "4.2": 6,
    "4.3": 22
  },
  "invoices_by_status": {
    "paid": 81,
    "failed": 7,
    "refunded": 1
  },
  "invoices_by_currency": {
    "USD": 87,
    "INR": 2
  },
  "accounts_by_invoice_count": {
    "0": 9,
    "2": 13,
    "3": 2,
    "4": 4,
    "5": 7,
    "6": 1
  },
  "usage_rows_by_period": {
    "2026-08": 32,
    "2026-09": 32,
    "2026-10": 32
  },
  "platform_status": {
    "api": "operational",
    "workflow-engine": "operational",
    "connectors": "degraded",
    "billing": "operational",
    "webhooks": "outage",
    "auth": "operational"
  }
}
```

## LLM generation

Calls: 105; prompt tokens: 135036; completion tokens: 48920; accepted first try: 2; after retry: 3; fell back to seeded: A1004, A1005, A1006, A1007, A1008, A1009, A1010, A1011, A1012, A1013, A1014, A1016, A1017, A1018, A1019, A1020, A1021, A1022, A1023, A1024, A1025, A1026, A1027, A1028, A1029, A1030, A1031, A1032, A1033, A1034, A1035, A1036

| Target | Attempt | Outcome | Problems |
|---|---|---|---|
| A1002 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1003 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1003 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1004 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1004 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1004 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1005 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1005 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1005 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1006 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1006 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1006 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1007 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1007 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1007 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1008 | 1 | schema_error | account.product_version: Value error, must look like 4.3 or 3.9.1 |
| A1008 | 2 | conformance_error | invoice INV-6028 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1008 | 3 | conformance_error | invoice INV-6028 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1009 | 1 | schema_error | account.product_version: Value error, must look like 4.3 or 3.9.1 |
| A1009 | 2 | conformance_error | account.product_version must be exactly '4.1'; invoice INV-6032 is failed and needs a failure_reason; invoice INV-6033 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1009 | 3 | conformance_error | invoice INV-6032 is failed and needs a failure_reason; invoice INV-6033 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1010 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1010 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1010 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1011 | 1 | conformance_error | usage 2026-10.workflow_runs must stay below the plan limit 20000; usage 2026-10.seats_used must stay below the plan limit 10; owner_email is already used by another account; choose a different one |
| A1011 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1011 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1012 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1012 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1012 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1013 | 1 | conformance_error | usage 2026-10.workflow_runs must stay below the plan limit 1000000; usage 2026-10.api_calls_peak_per_min must stay below the plan limit 10000; owner_email is already used by another account; choose a different one |
| A1013 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1013 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1014 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1014 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1014 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1015 | 1 | schema_error | account.product_version: Value error, must look like 4.3 or 3.9.1 |
| A1016 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1016 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1016 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1017 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1017 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1017 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1018 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1018 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1018 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1019 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1019 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1019 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1020 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1020 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1020 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1021 | 1 | conformance_error | usage 2026-10.workflow_runs must stay below the plan limit 1000000; usage 2026-10.api_calls_peak_per_min must stay below the plan limit 10000; invoice INV-6063 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1021 | 2 | conformance_error | invoice INV-6063 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1021 | 3 | conformance_error | invoice INV-6063 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1022 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1022 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1022 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1023 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1023 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1023 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1024 | 1 | conformance_error | invoice INV-6070 is failed and needs a failure_reason; invoice INV-6071 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1024 | 2 | conformance_error | invoice INV-6070 is failed and needs a failure_reason; invoice INV-6071 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1024 | 3 | conformance_error | invoice INV-6070 is failed and needs a failure_reason; invoice INV-6071 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1025 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1025 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1025 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1026 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1026 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1026 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1027 | 1 | conformance_error | usage 2026-10.workflow_runs must stay below the plan limit 1000000; usage 2026-10.api_calls_peak_per_min must stay below the plan limit 10000; invoice INV-6081 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1027 | 2 | conformance_error | invoice INV-6081 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1027 | 3 | conformance_error | invoice INV-6081 is failed and needs a failure_reason; owner_email is already used by another account; choose a different one |
| A1028 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1028 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1028 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1029 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1029 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1029 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1030 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1030 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1030 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1031 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1031 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1031 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1032 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1032 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1032 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1033 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1033 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1033 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1034 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1034 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1034 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1035 | 1 | conformance_error | usage 2026-10.workflow_runs must stay below the plan limit 1000000; usage 2026-10.api_calls_peak_per_min must stay below the plan limit 10000; owner_email is already used by another account; choose a different one |
| A1035 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1035 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
| A1036 | 1 | conformance_error | owner_email is already used by another account; choose a different one |
| A1036 | 2 | conformance_error | owner_email is already used by another account; choose a different one |
| A1036 | 3 | conformance_error | owner_email is already used by another account; choose a different one |
