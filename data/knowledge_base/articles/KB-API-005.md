# Connecting Salesforce

## Connecting in 4.x

To connect CloudFlow to Salesforce in version 4.x, go to **Connections > New connection > Salesforce** and sign in using OAuth. CloudFlow requests the scopes `api` and `refresh_token`. If Salesforce revokes access, you can reconnect by opening the connection and clicking **Reconnect**. Workflows that use this connection will retain their configuration.

## Connecting in 3.x

In CloudFlow 3.x, you can connect to Salesforce by entering a username, password, and Salesforce security token in **Connections > Salesforce > Edit**. After changing your Salesforce password, you must re-enter both the password and a new security token.

## Related errors

`CF-503` indicates that CloudFlow could not reach Salesforce or the connection is no longer authorized; see KB-TRB-002. `CF-502` means Salesforce returned an unexpected response.
