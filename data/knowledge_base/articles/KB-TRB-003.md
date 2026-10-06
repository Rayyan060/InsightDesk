# Workflow runs stuck in Queued

## Why runs queue

Runs wait in **Queued** status when the workflow engine is busy, when a platform incident affects the `workflow-engine` component, or when the account is suspended (KB-BIL-004).

## What to do

1. Check the platform status for the `workflow-engine` component.
2. Ensure the account is active.
3. Queued runs will start automatically once the issue is resolved; do not re-trigger them, as doing so may cause them to run twice.
