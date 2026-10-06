"""Help-center articles (doc_type ``article``, authority level 1).

Section 4.1 categories: getting started, account and billing, API and
integrations, troubleshooting (with error codes), advanced features. IDs and
details from the guide's own examples are reused: KB-ADV-007 (4.2+, section
"Steps", 2026-09-10), KB-API-014 ("Rotating API tokens", 4.0+, 2026-08-20,
supersedes KB-API-009) and KB-BIL-003 (section "Duplicate charges").

Version facts used consistently across the knowledge base:

* 3.x: Classic editor; API keys sent in ``X-CloudFlow-Key`` against ``/v1``;
  5-minute step timeout; cron triggers; run-history export from Settings > Data
  (CSV, up to 10,000 rows). Standard support ended 2026-06-30.
* 4.0: Flow editor; API tokens (``Authorization: Bearer``) against ``/v2``;
  OAuth connectors with Reconnect; per-step retry policies; 10-minute step timeout.
* 4.1: Schedules replace cron triggers (cron triggers stopped on 2026-06-30).
* 4.2: run-history export redesign (CSV or JSON, scheduled exports); 15-minute
  step timeout; 24-hour grace period when rotating API tokens.
* 4.3 (2026-09-15): legacy 3.x API keys stop working on 2026-12-01.
"""

from app.knowledge.catalog import DocSpec

_ALL = "all"

ARTICLES: tuple[DocSpec, ...] = (
    # ------------------------------------------------------------------ getting started
    DocSpec(
        "KB-GS-001", "article", "Getting started with CloudFlow", "getting_started", "4.0+", "2026-05-12",
        (
            ("Overview",
             "CloudFlow automates work between the apps your team already uses. A **workflow** is a trigger followed by one or "
             "more steps. Each time the trigger fires, CloudFlow starts a **run** and records it in run history."),
            ("Steps",
             "1. Sign in and create a workspace (Settings > Workspaces > New workspace).\n"
             "2. Open **Workflows > New workflow**. The Flow editor opens.\n"
             "3. Choose a trigger: an app event, a webhook or a schedule (KB-ADV-004).\n"
             "4. Add steps with **+ Add step**, then connect the apps each step needs (KB-API-005, KB-API-006).\n"
             "5. Click **Test run** to run once with sample data, then **Publish**."),
            ("Version differences",
             "CloudFlow 3.x uses the Classic editor: workflows are created from **Automations > Create** and published with "
             "**Activate**. The concepts are the same, but menus differ throughout. Check your version in Settings > About."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-GS-002", "article", "Inviting teammates and managing seats", "getting_started", _ALL, "2026-06-03",
        (
            ("Overview",
             "Each person who signs in to a workspace uses one seat. Your plan sets the number of seats (KB-POL-002): Free 2, "
             "Pro 10, Business 50, Enterprise 500."),
            ("Inviting a teammate",
             "Go to **Settings > Members > Invite**, enter the person's email address and choose a role (KB-GS-004). The invite "
             "is valid for 7 days. A pending invite does not use a seat until it is accepted."),
            ("When you run out of seats",
             "When every seat is in use, new invites are blocked with the message \"Seat limit reached\". Remove members you no "
             "longer need (Settings > Members > ... > Remove) or change plan (KB-BIL-006). Removing a member never deletes the "
             "workflows they built."),
        ),
    ),
    DocSpec(
        "KB-GS-003", "article", "Building your first workflow", "getting_started", "4.0+", "2026-05-12",
        (
            ("Overview",
             "This walkthrough builds a workflow that posts a Slack message whenever a new lead is created in Salesforce."),
            ("Steps",
             "1. Open **Workflows > New workflow** and name it \"New lead alert\".\n"
             "2. Trigger: choose **Salesforce > New record**, object **Lead**.\n"
             "3. Click **+ Add step** and choose **Slack > Send message**.\n"
             "4. Map the lead's name and company into the message using the **Insert field** picker.\n"
             "5. Click **Test run**, check the message in Slack, then **Publish**."),
            ("Tips",
             "Use **Step settings > Retry policy** to retry a failing step automatically (KB-ADV-001). Keep secrets in the "
             "workspace vault rather than typing them into step fields (KB-ADV-002)."),
        ),
    ),
    DocSpec(
        "KB-GS-004", "article", "Workspace roles and permissions", "getting_started", _ALL, "2026-02-20",
        (
            ("Roles",
             "| Role | Can do |\n|---|---|\n"
             "| Owner | Everything, including billing, plan changes and account deletion requests |\n"
             "| Admin | Manage members, connections and all workflows |\n"
             "| Editor | Create and edit workflows, view run history |\n"
             "| Viewer | View workflows and run history |\n\n"
             "Each account has exactly one owner. Billing questions about invoices are answered for the account owner and admins."),
            ("Changing a role",
             "Admins and the owner can change roles in **Settings > Members**. Ownership transfer requires the current owner to "
             "confirm by email."),
        ),
    ),
    # ------------------------------------------------------------------ account & billing
    DocSpec(
        "KB-ACC-001", "article", "Resetting your password", "account_billing", _ALL, "2026-08-20",
        (
            ("How it works",
             "Click **Forgot password?** on the sign-in page, or ask support to start a reset. CloudFlow emails a single-use "
             "reset link to the owner email address on file. The link expires after 30 minutes."),
            ("What support can and cannot do",
             "Support can trigger the reset email for the account you are signed in with. We will never show, type or paste a "
             "reset link or token in chat, and we cannot send it to a different email address (KB-POL-005)."),
            ("If the email does not arrive",
             "Check your spam folder and wait 5 minutes. Each new request invalidates the previous link. After 5 failed sign-in "
             "attempts, sign-in is locked for 15 minutes (KB-ACC-002)."),
        ),
    ),
    DocSpec(
        "KB-ACC-002", "article", "Two-factor authentication and sign-in lockouts", "account_billing", "4.0+", "2026-03-09",
        (
            ("Turning on two-factor authentication",
             "Go to **Profile > Security > Two-factor authentication** and scan the QR code with an authenticator app. Save the "
             "10 recovery codes somewhere safe. Owners of Business and Enterprise workspaces can require 2FA for every member."),
            ("Sign-in lockouts",
             "After 5 failed sign-in attempts, sign-in is locked for 15 minutes. Waiting is the fastest fix; support cannot "
             "shorten a lockout."),
            ("Version differences",
             "CloudFlow 3.x supports SMS codes only, from **My account > Security**. Authenticator apps require 4.0 or later."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-BIL-001", "article", "Plans and pricing", "account_billing", _ALL, "2026-08-01",
        (
            ("Plans",
             "CloudFlow has four plans: Free, Pro, Business and Enterprise. Prices and limits are defined in KB-POL-002. Free "
             "is never charged; paid plans are billed monthly in advance on the day of the month you first subscribed."),
            ("Upgrading",
             "An upgrade takes effect immediately. You are charged the full monthly price of the new plan on the day of the "
             "upgrade, and that day becomes your new billing day. Limits increase at once."),
            ("Downgrading",
             "A downgrade takes effect at the start of your next billing period. If you use more seats than the new plan allows, "
             "remove members first (KB-GS-002)."),
        ),
    ),
    DocSpec(
        "KB-BIL-002", "article", "Understanding your invoice", "account_billing", _ALL, "2026-04-18",
        (
            ("Invoice fields",
             "Each invoice shows an invoice number (for example INV-6001), the amount, the currency (USD, or INR for accounts "
             "billed in India), the charge date, the status and the last four digits of the card charged. CloudFlow never "
             "stores or shows full card numbers."),
            ("Invoice statuses",
             "| Status | Meaning |\n|---|---|\n"
             "| paid | The charge succeeded |\n"
             "| failed | The charge was declined; see KB-BIL-004 |\n"
             "| refunded | A refund approved by the billing team was issued |\n"),
            ("Finding invoices",
             "Owners and admins can see every invoice in **Settings > Billing > Invoices** and download a PDF of each."),
        ),
    ),
    DocSpec(
        "KB-BIL-003", "article", "Duplicate and unrecognised charges", "account_billing", _ALL, "2026-07-01",
        (
            ("Duplicate charges",
             "A duplicate charge is two paid invoices for the same amount on the same day when only one was expected. It most "
             "often happens when a payment is retried while the first attempt was still processing. Duplicate charges are always "
             "reviewed by the billing team, whatever their age, and the duplicate is refunded once a person confirms it. The "
             "assistant can find the two invoices and pass them to billing, but it cannot reverse a charge itself (KB-POL-006)."),
            ("Unrecognised charges",
             "Check **Settings > Billing > Invoices** for the invoice number on your statement. Upgrades are charged on the day "
             "they happen (KB-BIL-001), which is the most common reason for an unexpected charge."),
            ("What happens next",
             "The billing queue replies within 1 business day (KB-POL-003). Please do not open a chargeback while the review is "
             "in progress; a chargeback freezes the invoice."),
        ),
    ),
    DocSpec(
        "KB-BIL-004", "article", "Failed payments and past-due accounts", "account_billing", _ALL, "2026-05-27",
        (
            ("What happens when a payment fails",
             "If a charge is declined, the invoice is marked **failed** with a reason such as card_declined, insufficient_funds "
             "or expired_card, and the account becomes **past_due**. Workflows keep running while the account is past due."),
            ("Suspension",
             "If the next monthly charge also fails, the account is **suspended**: workflows stop and new runs are rejected until "
             "the balance is paid. Data is kept while an account is suspended."),
            ("Fixing it",
             "Update the card in **Settings > Billing > Payment method**, then click **Retry payment** on the failed invoice. The "
             "account returns to active as soon as the payment succeeds."),
        ),
    ),
    DocSpec(
        "KB-BIL-005", "article", "Requesting a refund", "account_billing", _ALL, "2026-09-15",
        (
            ("Before you ask",
             "Refund eligibility is set by the refund policy (KB-POL-001): only paid invoices, within 14 days for Pro and "
             "Business or 30 days for Enterprise. From 1 November 2026 the Pro and Business window becomes 7 days."),
            ("How to ask",
             "Tell support which invoice you want refunded. The assistant checks the invoice against the policy and hands the "
             "request to the billing team with the details. A person on the billing team makes every refund decision; the "
             "assistant never promises a refund."),
            ("After you ask",
             "Billing replies within 1 business day. Approved refunds return to the original card within 5 to 10 business days "
             "and the invoice status changes to refunded."),
        ),
    ),
    DocSpec(
        "KB-BIL-006", "article", "Changing or cancelling your plan", "account_billing", _ALL, "2026-04-02",
        (
            ("Changing plan",
             "Owners change plan in **Settings > Billing > Plan**. Upgrades apply immediately; downgrades apply at the next "
             "billing date (KB-BIL-001)."),
            ("Cancelling",
             "Cancel in **Settings > Billing > Cancel subscription**. No further invoices are created after cancellation, "
             "workflows stop at the end of the paid period, and the workspace becomes read-only. Cancelling does not delete "
             "your data; to delete an account see KB-POL-004."),
        ),
    ),
    # ------------------------------------------------------------------ API & integrations
    DocSpec(
        "KB-API-001", "article", "CloudFlow REST API overview", "api_integrations", "4.0+", "2026-04-14",
        (
            ("Base URL and authentication",
             "The 4.x API is served at `https://api.cloudflow.example/v2`. Authenticate every request with an API token in the "
             "header `Authorization: Bearer <token>`. Create tokens in **Settings > API tokens** and give each one only the "
             "scopes it needs, for example `workflows:read` or `runs:write`."),
            ("Common endpoints",
             "| Method | Path | Purpose |\n|---|---|---|\n"
             "| GET | `/v2/workflows` | List workflows |\n"
             "| POST | `/v2/workflows/{id}/runs` | Start a run |\n"
             "| GET | `/v2/runs/{id}` | Run status and output |\n"
             "| GET | `/v2/runs/export` | Export run history (4.2 and later) |\n"),
            ("Limits and errors",
             "Requests are limited per minute by plan (KB-API-003). Errors return a JSON body with a CloudFlow error code such "
             "as `CF-401` or `CF-429`; see the error reference KB-TRB-001."),
            ("Version differences",
             "CloudFlow 3.x uses the `/v1` API with legacy API keys (KB-API-002). `/v1` requests are not accepted by 4.x "
             "workspaces."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-API-002", "article", "Legacy API keys (CloudFlow 3.x)", "api_integrations", "3.x", "2026-09-15",
        (
            ("Overview",
             "CloudFlow 3.x authenticates API calls to `/v1` with a single workspace API key sent in the header "
             "`X-CloudFlow-Key`. Keys are managed in **Settings > Developer > API keys**."),
            ("Regenerating a key",
             "Click **Regenerate**. The old key stops working immediately, so update every integration at the same time."),
            ("Deprecation",
             "Legacy API keys are deprecated. They stop working on **1 December 2026** (announced in RN-2026-09). To keep using "
             "the API, upgrade the workspace to CloudFlow 4.x and switch to API tokens (KB-API-001)."),
        ),
        deprecated_on="2026-12-01",
        labels=("version_specific", "deprecation_upcoming"),
    ),
    DocSpec(
        "KB-API-003", "article", "API rate limits and 429 errors", "api_integrations", _ALL, "2026-08-01",
        (
            ("Limits by plan",
             "| Plan | API requests per minute |\n|---|---|\n| Free | 60 |\n| Pro | 600 |\n| Business | 3,000 |\n"
             "| Enterprise | 10,000 |\n\n"
             "The limit applies per workspace across all tokens or keys (KB-POL-002)."),
            ("What a 429 means",
             "A request over the limit receives HTTP 429 with error `CF-429` and a `Retry-After` header giving the seconds to "
             "wait. Requests are rejected, not queued."),
            ("Fixing 429 errors",
             "1. Respect `Retry-After` and back off exponentially.\n"
             "2. Spread scheduled jobs so they do not all start on the same minute.\n"
             "3. Use the bulk endpoints instead of one call per record.\n"
             "4. Compare your peak per-minute usage with your plan limit (support can look this up for you).\n\n"
             "Support cannot raise the limit for an individual workspace; a higher limit requires a plan change."),
        ),
    ),
    DocSpec(
        "KB-API-009", "article", "Rotating API tokens", "api_integrations", "4.0+", "2025-11-03",
        (
            ("Steps",
             "1. Go to **Settings > API tokens**.\n"
             "2. Click **Rotate** next to the token.\n"
             "3. Copy the new token and update your integrations.\n\n"
             "The old token is revoked immediately, so plan a short maintenance window."),
        ),
        labels=("superseded",),
        note="Superseded by KB-API-014 (24-hour grace period from 4.2).",
    ),
    DocSpec(
        "KB-API-014", "article", "Rotating API tokens", "api_integrations", "4.0+", "2026-08-20",
        (
            ("Overview",
             "Rotate API tokens regularly and immediately if a token may have been exposed (KB-POL-005)."),
            ("Rotating in 4.2 and later",
             "1. Go to **Settings > API tokens** and click **Rotate**.\n"
             "2. Copy the new token and update your integrations.\n"
             "3. The old token keeps working for a **24-hour grace period**, then is revoked automatically. Click **Revoke now** "
             "to end the grace period early, for example after a leak."),
            ("Rotating in 4.0 and 4.1",
             "The grace period does not exist before 4.2: the old token is revoked as soon as you click **Rotate**. Update "
             "integrations straight away."),
        ),
        supersedes=("KB-API-009",),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-API-004", "article", "Webhooks", "api_integrations", "4.0+", "2026-06-22",
        (
            ("Receiving webhooks",
             "Create a webhook trigger in a workflow to get a unique URL. CloudFlow accepts `POST` requests with a JSON body up "
             "to 1 MB."),
            ("Verifying signatures",
             "Outgoing webhooks are signed with HMAC-SHA256 in the `X-CloudFlow-Signature` header using your webhook secret. "
             "After you rotate the secret in **Settings > Webhooks**, update your receiver or every delivery will fail "
             "signature checks."),
            ("Retries",
             "Failed deliveries are retried 5 times over about 1 hour with exponential backoff. Check **Settings > Webhooks > "
             "Deliveries** for the response your endpoint returned."),
        ),
    ),
    DocSpec(
        "KB-API-005", "article", "Connecting Salesforce", "api_integrations", _ALL, "2026-04-14",
        (
            ("Connecting in 4.x",
             "Go to **Connections > New connection > Salesforce** and sign in with OAuth. CloudFlow requests the scopes `api` and "
             "`refresh_token`. If Salesforce revokes access, open the connection and click **Reconnect**; workflows that use it "
             "keep their configuration."),
            ("Connecting in 3.x",
             "CloudFlow 3.x connects with a username, password and Salesforce security token in **Connections > Salesforce > "
             "Edit**. After a Salesforce password change you must re-enter both the password and a new security token."),
            ("Related errors",
             "`CF-503` means CloudFlow could not reach Salesforce or the connection is no longer authorised; see KB-TRB-002. "
             "`CF-502` means Salesforce returned an unexpected response."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-API-006", "article", "Slack and Microsoft Teams connectors", "api_integrations", "4.0+", "2026-03-02",
        (
            ("Slack",
             "Connect in **Connections > New connection > Slack** and choose the channels CloudFlow may post to. Private "
             "channels require inviting the CloudFlow app to the channel."),
            ("Microsoft Teams",
             "Connect with a Microsoft 365 account that can install apps. Messages are posted as the CloudFlow bot."),
            ("Limits",
             "Slack limits apps to about 1 message per second per channel; CloudFlow queues messages to stay within it."),
        ),
    ),
    DocSpec(
        "KB-API-008", "article", "Supported integrations", "api_integrations", _ALL, "2026-09-01",
        (
            ("Connector catalog",
             "CloudFlow 4.x includes native connectors for Salesforce, HubSpot, Slack, Microsoft Teams, Google Sheets, Gmail, "
             "Jira, Zendesk, Stripe, Shopify, PostgreSQL and Amazon S3. CloudFlow 3.x supports Salesforce, Slack, Google Sheets "
             "and Gmail."),
            ("Apps without a connector",
             "Any service with an HTTP API can be used with the **HTTP request** step and a webhook trigger. CloudFlow does not "
             "build custom connectors on request, and an app that is not listed here is not supported natively."),
        ),
    ),
    # ------------------------------------------------------------------ troubleshooting
    DocSpec(
        "KB-TRB-001", "article", "CloudFlow error code reference", "troubleshooting", _ALL, "2026-09-10",
        (
            ("How to read an error",
             "Every failed API call or step shows a CloudFlow error code (CF-xxx), a message and a request ID. Quote the request "
             "ID when you contact support."),
            ("Error codes",
             "| Code | Meaning | What to do |\n|---|---|---|\n"
             "| CF-400 | The request body or step input is invalid | Check the fields named in the message |\n"
             "| CF-401 | Missing, expired or revoked API token or key | Create or rotate a token (KB-API-014) |\n"
             "| CF-402 | Free plan monthly workflow-run limit reached | Wait for the next month or upgrade (KB-TRB-007) |\n"
             "| CF-403 | The token's scope or the member's role does not allow this action | Add the scope or change the role (KB-TRB-004) |\n"
             "| CF-404 | Workflow, run or connection not found | Check the ID and workspace |\n"
             "| CF-409 | The workflow was edited while the run was starting | Retry the run |\n"
             "| CF-429 | API rate limit exceeded | Back off using `Retry-After` (KB-API-003) |\n"
             "| CF-500 | Internal CloudFlow error | Retry; check the status page |\n"
             "| CF-502 | A connected app returned an unexpected response | Check the app's own status |\n"
             "| CF-503 | A connected app is unreachable or the connection is no longer authorised | See KB-TRB-002 |\n"
             "| CF-504 | A step exceeded its time limit | See KB-TRB-006 |\n"),
            ("Platform incidents",
             "If many workflows fail with CF-500 or CF-503 at the same time, check platform status first; the support assistant "
             "can look it up for you."),
        ),
        labels=("error_code_table", "long"),
    ),
    DocSpec(
        "KB-TRB-002", "article", "Fixing CF-503 errors in Salesforce steps", "troubleshooting", _ALL, "2026-06-30",
        (
            ("Cause",
             "`CF-503` in a Salesforce step means CloudFlow could not complete the call: Salesforce was unreachable, or the "
             "connection's authorisation was revoked (for example after a password change or an admin policy change)."),
            ("Fix in 4.x",
             "1. Check platform status for a `connectors` incident; if there is one, wait for it to be resolved.\n"
             "2. Open **Connections > Salesforce** and click **Reconnect**, then sign in again. Do not delete the connection: "
             "deleting it unlinks every workflow that uses it.\n"
             "3. Re-run the failed run from run history."),
            ("Fix in 3.x",
             "Open **Connections > Salesforce > Edit** and re-enter the password and a new Salesforce security token, then "
             "re-run. Certificate verification cannot be turned off: the option was removed in the 3.9.4 security update, and "
             "turning it off was never a safe fix."),
            ("Still failing?",
             "If `CF-503` continues after reconnecting and there is no incident, contact support with the run's request ID."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-TRB-003", "article", "Workflow runs stuck in Queued", "troubleshooting", _ALL, "2026-07-21",
        (
            ("Why runs queue",
             "Runs wait in **Queued** when the workflow engine is busy, when a platform incident affects the `workflow-engine` "
             "component, or when the account is suspended (KB-BIL-004)."),
            ("What to do",
             "1. Check platform status for the `workflow-engine` component.\n"
             "2. Check that the account is active.\n"
             "3. Queued runs start automatically once the cause clears; do not re-trigger them, or they will run twice."),
        ),
    ),
    DocSpec(
        "KB-TRB-004", "article", "Authentication and permission errors (CF-401, CF-403)", "troubleshooting", _ALL, "2026-08-20",
        (
            ("CF-401",
             "The token or key is missing, expired or revoked. In 4.x check **Settings > API tokens**; in 3.x check **Settings > "
             "Developer > API keys**. After a rotation in 4.2 and later the old token still works for 24 hours (KB-API-014)."),
            ("CF-403",
             "The request is authenticated but not allowed. Add the missing scope to the token (4.x) or ask an admin to change "
             "your role (KB-GS-004)."),
            ("Never share tokens",
             "Do not paste API tokens into support conversations or workflow step fields. If a token was exposed, revoke it and "
             "report a security incident (KB-POL-005)."),
        ),
    ),
    DocSpec(
        "KB-TRB-005", "article", "Webhook delivery failures", "troubleshooting", "4.0+", "2026-06-22",
        (
            ("Check the delivery log",
             "Open **Settings > Webhooks > Deliveries**. A 4xx response means your endpoint rejected the request; a timeout "
             "means it took longer than 10 seconds to answer."),
            ("Signature failures",
             "If your receiver rejects deliveries after a secret rotation, update the secret on the receiver (KB-API-004)."),
            ("Platform incidents",
             "During a `webhooks` incident, deliveries are paused and retried automatically once the incident is resolved. "
             "Check platform status before changing your endpoint."),
        ),
    ),
    DocSpec(
        "KB-TRB-006", "article", "Step timeouts (CF-504)", "troubleshooting", _ALL, "2026-04-14",
        (
            ("Time limits by version",
             "| Version | Step time limit |\n|---|---|\n| 3.x | 5 minutes |\n| 4.0-4.1 | 10 minutes |\n| 4.2 and later | 15 minutes |\n"),
            ("Fixing CF-504",
             "Split long steps into smaller ones, page through large record sets, and move slow external calls to an "
             "asynchronous pattern: start the job, then poll for the result in a later step. Time limits cannot be raised per "
             "workspace."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-TRB-007", "article", "Monthly workflow-run limit reached (CF-402)", "troubleshooting", _ALL, "2026-08-01",
        (
            ("Free plan",
             "When a Free workspace reaches 1,000 workflow runs in a month, new runs are rejected with `CF-402` until the first "
             "day of the next month (UTC) or until you upgrade."),
            ("Paid plans",
             "Pro, Business and Enterprise workspaces keep running past the monthly limit. Usage over the limit is shown as over "
             "quota in **Settings > Usage**, and repeated overage is a reason to change plan. Exactly at the limit is not over "
             "quota (KB-POL-002)."),
            ("Checking usage",
             "**Settings > Usage** shows workflow runs this month, peak API requests per minute and seats in use. Support can "
             "look up the same figures."),
        ),
    ),
    # ------------------------------------------------------------------ advanced features
    DocSpec(
        "KB-ADV-001", "article", "Error handling and retry policies", "advanced", "4.0+", "2026-05-05",
        (
            ("Retry policies",
             "In 4.x every step has **Step settings > Retry policy**: up to 5 retries with fixed or exponential backoff. Retries "
             "apply to CF-500, CF-502, CF-503 and CF-504 errors, never to CF-400 or CF-403."),
            ("Error branches",
             "Add an **On error** branch to a step to send an alert or write the failed record somewhere for review."),
            ("Version differences",
             "CloudFlow 3.x has no per-step retries; the whole workflow can be retried from run history."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-ADV-002", "article", "Variables and the secrets vault", "advanced", "4.0+", "2026-05-05",
        (
            ("Variables",
             "Store values you reuse, such as a channel name, as workspace variables in **Settings > Variables**."),
            ("Secrets vault",
             "Store credentials in **Settings > Vault**. Vault values are encrypted, masked in run history and never shown "
             "again after you save them. Reference them in steps as `{{vault.NAME}}`."),
        ),
    ),
    DocSpec(
        "KB-ADV-003", "article", "Cron triggers", "advanced", "3.x, 4.0", "2026-02-02",
        (
            ("Overview",
             "Cron triggers start a workflow on a cron expression set in **Settings > Triggers > Cron**."),
            ("Deprecation",
             "Cron triggers are deprecated in CloudFlow 4.1 and stop working on 30 June 2026. Move to Schedules (KB-ADV-004)."),
        ),
        effective_from="2024-05-06",  # cron triggers date from CloudFlow 3.8
        deprecated_on="2026-06-30",
        labels=("deprecated", "version_specific"),
    ),
    DocSpec(
        "KB-ADV-004", "article", "Schedules", "advanced", "4.1+", "2026-07-01",
        (
            ("Overview",
             "Schedules start a workflow at fixed times, for example every weekday at 09:00 in your time zone. They replace cron "
             "triggers, which stopped working on 30 June 2026."),
            ("Steps",
             "1. Open the workflow and choose **Trigger > Schedule**.\n"
             "2. Pick a frequency or enter a cron expression in the **Advanced** tab.\n"
             "3. Choose the time zone and **Publish**."),
            ("Migrating from cron triggers",
             "Schedules require CloudFlow 4.1 or later. Workspaces on 3.x must upgrade to keep running time-based workflows."),
        ),
        effective_from="2026-02-02",
        supersedes=("KB-ADV-003",),
    ),
    DocSpec(
        "KB-ADV-005", "article", "Exporting run history in CloudFlow 3.x", "advanced", "3.x", "2025-03-11",
        (
            ("Steps",
             "1. Go to **Settings > Data > Export runs**.\n"
             "2. Choose a date range within the last 30 days.\n"
             "3. Click **Export CSV**. Exports are limited to 10,000 rows."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-ADV-006", "article", "Exporting run history in CloudFlow 4.0 and 4.1", "advanced", "4.0-4.1", "2025-11-03",
        (
            ("Steps",
             "1. Open **Workflows** and select the workflow.\n"
             "2. Open **Run history**.\n"
             "3. Click **Download CSV**. Downloads are limited to 50,000 rows per workflow."),
        ),
        labels=("version_specific",),
    ),
    DocSpec(
        "KB-ADV-007", "article", "Exporting workflow run history", "advanced", "4.2+", "2026-09-10",
        (
            ("Overview",
             "From CloudFlow 4.2 you can export run history for one or many workflows as CSV or JSON, once or on a schedule."),
            ("Steps",
             "1. Open **Workflows**, select the workflow, then open **Run history**.\n"
             "2. Click **Export** and choose **CSV** or **JSON**.\n"
             "3. Pick the date range and the columns to include.\n"
             "4. Click **Export now**, or **Schedule export** to receive the file by email every day or week.\n\n"
             "Exports are limited to 1,000,000 rows. Through the API use `GET /v2/runs/export`."),
            ("Retention",
             "Exports include runs still held in run history; retention depends on your plan (KB-ADV-008)."),
        ),
        labels=("version_specific", "long"),
    ),
    DocSpec(
        "KB-ADV-008", "article", "Run history retention", "advanced", _ALL, "2026-03-15",
        (
            ("Retention by plan",
             "| Plan | Run history kept |\n|---|---|\n| Free | 7 days |\n| Pro | 30 days |\n| Business | 90 days |\n"
             "| Enterprise | 365 days |\n"),
            ("After retention ends",
             "Older runs are deleted permanently. Export what you need before it expires (KB-ADV-007)."),
        ),
    ),
)
