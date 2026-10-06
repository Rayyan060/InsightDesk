# Authentication and permission errors (CF-401, CF-403)

## CF-401

The token or key is missing, expired or revoked. In 4.x check **Settings > API tokens**; in 3.x check **Settings > Developer > API keys**. After a rotation in 4.2 and later the old token still works for 24 hours (KB-API-014).

## CF-403

The request is authenticated but not allowed. Add the missing scope to the token (4.x) or ask an admin to change your role (KB-GS-004).

## Never share tokens

Do not paste API tokens into support conversations or workflow step fields. If a token was exposed, revoke it and report a security incident (KB-POL-005).
