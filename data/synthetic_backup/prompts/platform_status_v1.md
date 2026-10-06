Produce one row per component, in this order. Reference date: $reference_date.

$component_lines

Rules:
- component and status are FIXED.
- incident_id is FIXED where given, otherwise null (operational components have no incident).
- updated_at is FREE: a timestamp on the reference date between 00:00Z and 08:00Z.

Return a JSON object with key "rows" holding the list of rows.
