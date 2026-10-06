Generate the records for one CloudFlow customer account.

Reference date (today, for this dataset): $reference_date
Account scenario: $scenario - $description

ACCOUNT (copy FIXED values exactly):
- account_id: $account_id (FIXED)
- plan: $plan (FIXED)
- status: $status (FIXED)
- product_version: $product_version (FIXED)
- created_at: $created_at (FIXED)
- company_name: FREE - a plausible fictional company name, 2-4 words
- owner_email: FREE - fictional, must end with @example.com

PLAN LIMITS for $plan (for your reference):
$plan_limits

USAGE - produce exactly these monthly rows (period is FIXED):
$usage_lines

INVOICES - produce exactly these invoices (all listed fields FIXED):
$invoice_lines

Return a JSON object with keys "account", "usage" and "invoices", matching the schema.
