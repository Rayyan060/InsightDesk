# Webhook delivery failures

## Check the delivery log

Open **Settings > Webhooks > Deliveries**. A 4xx response indicates that your endpoint rejected the request, while a timeout suggests it took longer than 10 seconds to respond.

## Signature failures

If your receiver rejects deliveries after a secret rotation, update the secret on the receiver (KB-API-004).

## Platform incidents

During a `webhooks` incident, deliveries are paused and retried automatically once the incident is resolved. Check the platform status before changing your endpoint.
