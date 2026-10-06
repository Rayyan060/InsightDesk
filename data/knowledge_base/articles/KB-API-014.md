# Rotating API tokens

## Overview

Rotate API tokens regularly and immediately if a token may have been exposed (KB-POL-005).

## Rotating in 4.2 and later

1. Go to **Settings > API tokens** and click **Rotate**.
2. Copy the new token and update your integrations.
3. The old token keeps working for a **24-hour grace period**, then is revoked automatically. Click **Revoke now** to end the grace period early, for example after a leak.

## Rotating in 4.0 and 4.1

The grace period does not exist before 4.2: the old token is revoked as soon as you click **Rotate**. Update integrations straight away.
