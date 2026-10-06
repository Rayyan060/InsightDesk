# Synthetic data validation report

**Result:** PASS  
**Generator:** seeded; seed 20261006; reference date 2026-10-06

## Pipeline steps

| Step | Result | Detail |
|---|---|---|
| generate | ok | seeded generator, 36 accounts |
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
| active_within_quota | pass | A1001 | A1001, A1010, A1011, A1012, A1013, A1014, A1015, A1016 ... |
| approaching_quota | pass | A1002 | A1002 |
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
