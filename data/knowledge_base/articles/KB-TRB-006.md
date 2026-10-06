# Step timeouts (CF-504)

## Time limits by version

| Version | Step time limit |
|---|---|
| 3.x | 5 minutes |
| 4.0-4.1 | 10 minutes |
| 4.2 and later | 15 minutes |

## Fixing CF-504

Split long steps into smaller ones, page through large record sets, and move slow external calls to an asynchronous pattern: start the job, then poll for the result in a later step. Time limits cannot be raised per workspace.
