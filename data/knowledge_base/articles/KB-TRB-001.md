# CloudFlow error code reference

## How to read an error

Every failed API call or step shows a CloudFlow error code (CF-xxx), a message, and a request ID. When you contact support, make sure to quote the request ID.

## Error codes

| Code | Meaning | What to do |
|---|---|---|
| **CF-400** | The request body or step input is invalid | Check the fields named in the message |
| **CF-401** | Missing, expired, or revoked API token or key | Create or rotate a token (KB-API-014) |
| **CF-402** | Free plan monthly workflow-run limit reached | Wait for the next month or upgrade (KB-TRB-007) |
| **CF-403** | The token's scope or the member's role does not allow this action | Add the scope or change the role (KB-TRB-004) |
| **CF-404** | Workflow, run, or connection not found | Check the ID and workspace |
| **CF-409** | The workflow was edited while the run was starting | Retry the run |
| **CF-429** | API rate limit exceeded | Back off using `Retry-After` (KB-API-003) |
| **CF-500** | Internal CloudFlow error | Retry; check the status page |
| **CF-502** | A connected app returned an unexpected response | Check the app's own status |
| **CF-503** | A connected app is unreachable or the connection is no longer authorised | See KB-TRB-002 |
| **CF-504** | A step exceeded its time limit | See KB-TRB-006 |

## Platform incidents

If many workflows fail with CF-500 or CF-503 at the same time, check the platform status first. The support assistant can look it up for you.
