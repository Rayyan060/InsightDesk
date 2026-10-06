# Exporting workflow run history

## Overview

Starting from CloudFlow version 4.2, you can export the run history of one or more workflows as either CSV or JSON. You can export the history once or set up a schedule to receive the file by email on a daily or weekly basis.

## Steps

1. Navigate to **Workflows**, select the desired workflow, and then open **Run history**.
2. Click **Export** and choose between **CSV** or **JSON**.
3. Define the date range and select the columns you want to include.
4. Click **Export now** to generate the file immediately, or **Schedule export** to have it sent to your email on a set schedule.
Exports are limited to 1,000,000 rows. For API access, use the `GET /v2/runs/export` endpoint.

## Retention

Exported data includes runs still held in the run history. The retention period depends on your plan (KB-ADV-008).
