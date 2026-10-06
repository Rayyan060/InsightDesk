# Building your first workflow

## Overview

This walkthrough guides you through creating a workflow that sends a Slack message whenever a new lead is created in Salesforce.

## Steps

1. Open **Workflows > New workflow** and name your workflow "New lead alert".
2. Set the **Trigger** to **Salesforce > New record**, selecting **Lead** as the object.
3. Click **+ Add step** and choose **Slack > Send message**.
4. Use the **Insert field** picker to map the lead's name and company into the message.
5. Click **Test run**, check the message in Slack, and then **Publish**.

## Tips

Use **Step settings > Retry policy** to automatically retry a failing step (KB-ADV-001). Store secrets in the workspace vault rather than typing them into step fields (KB-ADV-002).
