# API rate limits and 429 errors

## Limits by plan

Here are the API request limits per minute for each CloudFlow plan:

| Plan | API requests per minute |
|---|---|
| Free | **60** |
| Pro | **600** |
| Business | **3,000** |
| Enterprise | **10,000** |

The limit applies per workspace across all tokens or keys (KB-POL-002).

## What a 429 means

When a request exceeds the API limit, it receives an HTTP 429 response with an error code `CF-429` and a `Retry-After` header indicating the number of seconds to wait before retrying. Requests are rejected, not queued.

## Fixing 429 errors

To handle 429 errors, follow these steps:

1. Respect the `Retry-After` header and back off exponentially.
2. Spread scheduled jobs so they do not all start on the same minute.
3. Use bulk endpoints instead of making one call per record.
4. Compare your peak per-minute usage with your plan limit (support can look this up for you).

Support cannot raise the limit for an individual workspace; a higher limit requires a plan change.
