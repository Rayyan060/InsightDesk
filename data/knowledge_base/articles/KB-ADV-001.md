# Error handling and retry policies

## Retry policies

In CloudFlow 4.x, every step has a **Step settings > Retry policy** that allows up to 5 retries with either fixed or exponential backoff. These retries apply to errors CF-500, CF-502, CF-503, and CF-504, but not to CF-400 or CF-403.

## Error branches

To handle errors, you can add an **On error** branch to a step. This branch can be used to send an alert or store the failed record for review.

## Version differences

In CloudFlow 3.x, there are no per-step retries. Instead, the entire workflow can be retried from the run history.
