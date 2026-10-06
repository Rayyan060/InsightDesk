# Webhooks

## Receiving webhooks

To set up a webhook in CloudFlow, create a trigger in a workflow that provides a unique URL. CloudFlow expects `POST` requests with a JSON body, limited to 1 MB.

## Verifying signatures

Outgoing webhooks from CloudFlow are signed using HMAC-SHA256 in the `X-CloudFlow-Signature` header with your webhook secret. After updating your webhook secret in **Settings > Webhooks**, ensure your receiver is updated to handle the new signature. Failure to do so will result in failed delivery checks.

## Retries

If a webhook delivery fails, CloudFlow will retry the delivery up to 5 times over approximately 1 hour, using exponential backoff. Check **Settings > Webhooks > Deliveries** for the response your endpoint returned.
