# Plans and usage limits

## Introduction

Every CloudFlow plan includes limits on API traffic, workflow runs, and seats. This policy outlines these limits and how usage is measured against them.

## Plan limits

Here are the limits for each CloudFlow plan:

| Plan | API Requests per Minute | Workflow Runs per Month | Seats | Support Tier | Monthly Price (USD) |
| --- | --- | --- | --- | --- | --- |
| Free | 60 | 1,000 | 2 | community | 0 |
| Pro | 600 | 20,000 | 10 | standard | 49 |
| Business | 3,000 | 150,000 | 50 | priority | 299 |
| Enterprise | 10,000 | 1,000,000 | 500 | priority | 1499 |

API requests per minute are measured across all API tokens in a workspace. Workflow runs reset on the first day of each calendar month (UTC). Plan limits are not adjusted on a case-by-case basis; a higher limit requires changing to a different plan.

## Usage limits

Usage is compared to the plan limit for the current period:

- **Over the limit** means usage is strictly greater than the plan limit. Usage exactly at the limit is **at the limit**, not over it.
- **Approaching the limit** means usage is at or above **0.8** (80%) of a limit but not over it.
- API requests above the per-minute limit receive error `CF-429` (see KB-API-003).
- When monthly workflow runs go over the limit, Free workspaces stop starting new runs (`CF-402`), while paid plans continue running and are flagged as over quota (see KB-TRB-007).

Usage figures quoted by support always come from CloudFlow's account tools, never from estimates.
