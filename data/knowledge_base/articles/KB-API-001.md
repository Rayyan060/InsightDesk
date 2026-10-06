# CloudFlow REST API overview

## Base URL and authentication

The 4.x API is served at `https://api.cloudflow.example/v2`. To authenticate each request, include an API token in the header `Authorization: Bearer <token>`. Create tokens in **Settings > API tokens** and assign them the necessary scopes, such as `workflows:read` or `runs:write`.

## Common endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v2/workflows` | List workflows |
| POST | `/v2/workflows/{id}/runs` | Start a run |
| GET | `/v2/runs/{id}` | Run status and output |
| GET | `/v2/runs/export` | Export run history (4.2 and later) |

## Limits and errors

Requests are limited per minute by plan (KB-API-003). Errors return a JSON body with a CloudFlow error code such as `CF-401` or `CF-429`; see the error reference KB-TRB-001.

## Version differences

CloudFlow 3.x uses the `/v1` API with legacy API keys (KB-API-002). `/v1` requests are not accepted by 4.x workspaces.
