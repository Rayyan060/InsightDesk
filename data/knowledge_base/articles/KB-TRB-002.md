# Fixing CF-503 errors in Salesforce steps

## Cause

`CF-503` in a Salesforce step means CloudFlow could not complete the call: Salesforce was unreachable, or the connection's authorisation was revoked (for example after a password change or an admin policy change).

## Fix in 4.x

1. Check platform status for a `connectors` incident; if there is one, wait for it to be resolved.
2. Open **Connections > Salesforce** and click **Reconnect**, then sign in again. Do not delete the connection: deleting it unlinks every workflow that uses it.
3. Re-run the failed run from run history.

## Fix in 3.x

Open **Connections > Salesforce > Edit** and re-enter the password and a new Salesforce security token, then re-run. Certificate verification cannot be turned off: the option was removed in the 3.9.4 security update, and turning it off was never a safe fix.

## Still failing?

If `CF-503` continues after reconnecting and there is no incident, contact support with the run's request ID.
