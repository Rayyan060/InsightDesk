"""Policy articles KB-POL-001 to KB-POL-006 (authority level 1).

Section titles are exactly the ``source_section`` values cited by
``data/reference/policy_registry.csv``, and every numeric registry value
appears in its cited section (checked by the validator). The plan-limits table
in KB-POL-002 must equal ``data/reference/plan_limits.csv`` (also checked).
"""

from app.knowledge.catalog import DocSpec

POLICIES: tuple[DocSpec, ...] = (
    DocSpec(
        "KB-POL-001", "policy", "Refund policy", "policy", "all", "2026-09-15",
        (
            ("Introduction",
             "This policy explains when a CloudFlow charge can be considered for a refund and who decides. "
             "It applies to every plan that is charged. Free plans are never charged, so they are never refunded."),
            ("Refund window",
             "A paid invoice can be considered for a refund only within the refund window for the account's plan:\n\n"
             "| Plan | Refund window |\n|---|---|\n| Pro | 14 days |\n| Business | 14 days |\n| Enterprise | 30 days |\n\n"
             "The window is counted in calendar days from the charge date. The charge date is day 0, so the **last day of the window "
             "is still eligible**: a Pro charge made on 22 September can be considered until the end of 6 October, and a charge made "
             "one day earlier cannot. The plan in force when the request is made determines the window."),
            ("Eligibility",
             "Only invoices with the status **paid** can be considered. A **failed** invoice was never collected, so there is nothing "
             "to refund. A **refunded** invoice has already been settled. Duplicate charges are always reviewed, whatever their "
             "age (see KB-BIL-003)."),
            ("Who approves refunds",
             "Refunds and credits are always approved by a person on the CloudFlow billing team. The support assistant can check "
             "whether an invoice is inside the window and pass the request to billing with the evidence, but it never issues, "
             "promises or schedules a refund or credit. Every refund request, eligible or not, goes to the billing queue."),
            ("Upcoming changes",
             "From **1 November 2026** the refund window for Pro and Business plans shortens to **7 days**. Charges made before "
             "that date keep the 14-day window that applied when they were made. The Enterprise window stays at 30 days."),
        ),
        labels=("policy",),
    ),
    DocSpec(
        "KB-POL-002", "policy", "Plans and usage limits", "policy", "all", "2026-08-01",
        (
            ("Introduction",
             "Every CloudFlow plan includes limits on API traffic, workflow runs and seats. This policy defines the limits and "
             "how usage is compared with them."),
            ("Plan limits",
             "| Plan | API requests per minute | Workflow runs per month | Seats | Support tier | Monthly price (USD) |\n"
             "|---|---|---|---|---|---|\n"
             "| Free | 60 | 1,000 | 2 | community | 0 |\n"
             "| Pro | 600 | 20,000 | 10 | standard | 49 |\n"
             "| Business | 3,000 | 150,000 | 50 | priority | 299 |\n"
             "| Enterprise | 10,000 | 1,000,000 | 500 | priority | 1,499 |\n\n"
             "API requests per minute is measured per workspace across all API tokens. Workflow runs reset on the first day of "
             "each calendar month (UTC). Limits are not raised case by case; a higher limit requires a plan change."),
            ("Usage limits",
             "Usage is compared with the plan limit for the current period:\n\n"
             "- **Over the limit** means usage is *strictly greater* than the plan limit. Usage exactly at the limit is "
             "**at the limit**, not over it.\n"
             "- **Approaching the limit** means usage is at or above **0.8** (80%) of a limit but not over it.\n"
             "- API requests above the per-minute limit receive error `CF-429` (see KB-API-003).\n"
             "- When monthly workflow runs go over the limit, Free workspaces stop starting new runs (`CF-402`), while paid "
             "plans keep running and are flagged as over quota (see KB-TRB-007).\n\n"
             "Usage figures quoted by support always come from CloudFlow's account tools, never from estimates."),
        ),
        labels=("policy",),
    ),
    DocSpec(
        "KB-POL-003", "policy", "Escalation and support response targets", "policy", "all", "2026-09-01",
        (
            ("Introduction",
             "The CloudFlow support assistant answers questions it can answer from current documentation and account tools. "
             "This policy defines when a conversation is handed to a person and how quickly people respond."),
            ("When we hand off",
             "A conversation is handed to a person with the full context when:\n\n"
             "- the request is a refund, credit, billing dispute, legal matter (contracts, subpoenas, data-processing agreements), "
             "security incident or account deletion;\n"
             "- at least 1 account tool that is required to answer has failed, because the assistant does not guess;\n"
             "- the documentation does not cover the question and the customer needs an outcome (otherwise the assistant says "
             "the topic is not covered and offers a handoff);\n"
             "- sources still conflict after the documentation has been checked against the customer's version and date.\n\n"
             "Answerable how-to and troubleshooting questions are not escalated."),
            ("Talking to a person",
             "Customers can always ask for a person, and an explicit request is honoured. A conversation is also handed off when "
             "the customer shows strong negative sentiment and has contacted us about the same issue at least 2 times, including "
             "the current contact."),
            ("Answer quality",
             "Every drafted answer is checked against its sources before it is sent. An answer is sent only when its groundedness "
             "score is at least 0.75. A draft that falls short may be revised at most 1 time; if it still falls short, the "
             "conversation is handed to a person instead of sending an unsupported answer."),
            ("Response targets",
             "First-response targets after a handoff:\n\n"
             "| Queue or support tier | First response within |\n|---|---|\n"
             "| Billing queue (refunds, disputes) | 1 business day |\n"
             "| Security queue | 1 hour |\n"
             "| Priority tier (Business, Enterprise) | 4 hours |\n"
             "| Standard tier (Pro) | 24 hours |\n"
             "| Community tier (Free) | 72 hours |\n\n"
             "Targets are measured from the time the handoff is created."),
        ),
        labels=("policy",),
    ),
    DocSpec(
        "KB-POL-004", "policy", "Account deletion policy", "policy", "all", "2026-06-10",
        (
            ("Introduction",
             "Deleting a CloudFlow account permanently removes its workspaces, workflows, run history and stored credentials."),
            ("Deletion requests",
             "Only the account owner can request deletion. The support assistant never deletes or schedules the deletion of an "
             "account. Every deletion request is handed to the account team, who verify the owner's identity through the email "
             "address on file before acting. After confirmation the account is disabled immediately and its data is erased "
             "within 30 days. Outstanding invoices are not cancelled by a deletion request."),
            ("Exporting data first",
             "Before requesting deletion, export anything you need: run history (KB-ADV-007) and workflow definitions "
             "(Workflows > ... > Export definition). Deleted data cannot be recovered."),
        ),
        labels=("policy",),
    ),
    DocSpec(
        "KB-POL-005", "policy", "Security and account access policy", "policy", "all", "2026-08-20",
        (
            ("Introduction",
             "This policy covers suspected security incidents, password resets and which account data support can discuss."),
            ("Reporting a security incident",
             "Treat any of the following as a security incident: a leaked or exposed API token, unexpected sign-ins, workflows you "
             "did not create, or a suspected compromise of a connected system. Report it to support immediately. Security reports "
             "go to the security queue at urgent priority and receive a first response within 1 hour (KB-POL-003). If a token "
             "may be exposed, revoke it at once in Settings > API tokens (4.x) or Settings > Developer (3.x); you do not need to "
             "wait for us."),
            ("Password resets",
             "Password resets are started only through CloudFlow's reset tool, which emails a single-use link to the owner email "
             "address on file for the account. The link expires after 30 minutes. Support staff and the assistant never see, "
             "type or paste reset links or tokens in a conversation, and the reset can never be redirected to another address."),
            ("Account access",
             "Support discusses only the account identified by the session you are signed in with. We do not disclose another "
             "account's plan, usage, invoices or contacts, even if you quote its account ID, and we refuse such requests."),
        ),
        labels=("policy",),
    ),
    DocSpec(
        "KB-POL-006", "policy", "Billing disputes policy", "policy", "all", "2026-07-01",
        (
            ("Introduction",
             "A billing dispute is any disagreement about a charge: a duplicate charge, a charge you do not recognise, a charge "
             "after cancellation, or an amount that does not match your plan."),
            ("When billing escalates",
             "Billing disputes, refund requests and credit requests are always handed to the billing queue, with the invoices "
             "involved attached as evidence. The assistant can look up invoices and explain what they show, but it cannot "
             "reverse charges, issue refunds or grant credits. The billing queue's first-response target is 1 business day "
             "(KB-POL-003)."),
            ("Chargebacks",
             "If you open a chargeback with your bank, the disputed invoice is frozen until the bank decides; we cannot refund it "
             "in parallel."),
        ),
        labels=("policy",),
    ),
)
