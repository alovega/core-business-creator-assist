# Audit Logs implementation
## Contract
`GET /api/audit-logs?limit=50&offset=0&action=message_sent`, requires access token, active business membership and `view_audit_logs` permission. Returns `audit_logs`, `total`, `limit`, `offset`. The server uses the authenticated business, not a client-provided business id query parameter.

Events: `login`, `message_sent`, `lead_updated`, `payment_marked_paid`, `booking_cancelled`, `automation_changed`. Metadata is strictly allowlisted; do not pass secrets, payloads, content, token values, payment references or contact details.

## Deployment and limitations
Run existing migration entrypoint (`RUN_MIGRATIONS=1`) before serving traffic. The source archive did not include `.git`; apply the patch to your real repository and create the branch there. Logging failures are caught and reported via server logger after primary state commits. As Pony uses a shared request transaction, a database-connection-level failure can still taint the request's session; **true failure isolation** needs a separate connection/queue/outbox. For strict audit reliability use a transactional outbox with a separate delivery worker. There is currently no audit for users logging in without a selected business, by design: unscoped logs would break tenant isolation.

## Local validation
`cd backend && python -m pytest app/audit_logs/tests -q`; run the entire suite before merging. Existing code runs via Flask/Pony ORM. Python environment here lacked Flask; tests could not execute.