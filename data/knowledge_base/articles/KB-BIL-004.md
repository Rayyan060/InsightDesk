# Failed payments and past-due accounts

## What happens when a payment fails

If a charge is declined, the invoice is marked **failed** with a reason such as `card_declined`, `insufficient_funds`, or `expired_card`, and the account becomes **past_due**. Workflows continue to run while the account is past due.

## Suspension

If the next monthly charge also fails, the account is **suspended**: workflows stop and new runs are rejected until the balance is paid. Data remains available while an account is suspended.

## Fixing it

To fix the issue, update the card in **Settings > Billing > Payment method**, then click **Retry payment** on the failed invoice. The account will return to an active state as soon as the payment is successful.
