# Escalation and support response targets

## Introduction

The CloudFlow support assistant answers questions it can answer from current documentation and account tools. This policy defines when a conversation is handed to a person and how quickly people respond.

## When we hand off

A conversation is handed to a person with the full context when:

- the request is a refund, credit, billing dispute, legal matter (contracts, subpoenas, data-processing agreements), security incident or account deletion;
- at least 1 account tool that is required to answer has failed, because the assistant does not guess;
- the documentation does not cover the question and the customer needs an outcome (otherwise the assistant says the topic is not covered and offers a handoff);
- sources still conflict after the documentation has been checked against the customer's version and date.

Answerable how-to and troubleshooting questions are not escalated.

## Talking to a person

Customers can always ask for a person, and an explicit request is honoured. A conversation is also handed off when the customer shows strong negative sentiment and has contacted us about the same issue at least 2 times, including the current contact.

## Answer quality

Every drafted answer is checked against its sources before it is sent. An answer is sent only when its groundedness score is at least 0.75. A draft that falls short may be revised at most 1 time; if it still falls short, the conversation is handed to a person instead of sending an unsupported answer.

## Response targets

First-response targets after a handoff:

| Queue or support tier | First response within |
|---|---|
| Billing queue (refunds, disputes) | 1 business day |
| Security queue | 1 hour |
| Priority tier (Business, Enterprise) | 4 hours |
| Standard tier (Pro) | 24 hours |
| Community tier (Free) | 72 hours |

Targets are measured from the time the handoff is created.
