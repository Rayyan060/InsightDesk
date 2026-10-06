Rewrite this resolved CloudFlow support ticket so it reads like a real
customer conversation summary. Keep the customer's tone (angry customers stay
angry), keep every fact (versions, error codes, menu paths, numbers), and do
not change what the agent actually did, even if it was wrong. This is a
historical record.

Subject: $subject
Product version: $product_version
Intent: $intent

Customer question (FACTS):
$customer_question

Resolution (FACTS):
$resolution

Return a JSON object: {"customer_question": "...", "resolution": "..."}
