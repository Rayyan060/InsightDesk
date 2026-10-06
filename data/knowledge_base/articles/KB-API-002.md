# Legacy API keys (CloudFlow 3.x)

## Overview

CloudFlow 3.x uses a single workspace API key, sent in the header `X-CloudFlow-Key`, to authenticate API calls to `/v1`. These keys are managed in **Settings > Developer > API keys**.

## Regenerating a key

To regenerate a key, click **Regenerate**. The old key will stop working immediately, so be sure to update every integration at the same time.

## Deprecation

Legacy API keys are deprecated and will stop working on **1 December 2026** (announced in RN-2026-09). To continue using the API, upgrade your workspace to CloudFlow 4.x and switch to API tokens (KB-API-001).
