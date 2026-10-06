# Monthly workflow-run limit reached (CF-402)

## Free plan

When a Free workspace reaches 1,000 workflow runs in a month, any additional runs will be rejected with the error code `CF-402`. Runs will resume on the first day of the next month (UTC) or after you upgrade your plan.

## Paid plans

Pro, Business, and Enterprise workspaces can continue running beyond the monthly limit. Overages will be shown as over quota in **Settings > Usage**. Repeated overages may be a reason to consider upgrading your plan. However, exactly at the limit is not considered over quota (KB-POL-002).

## Checking usage

To check your workflow runs, peak API requests per minute, and seats in use, go to **Settings > Usage**. Support can also access this information.
