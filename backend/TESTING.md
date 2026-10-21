# Backend testing foundation

Run the full suite from the repository root:

```bash
make test
```

Or, if dependencies are already installed, run from `backend/`:

```bash
python -m pytest app -v
```

`backend/app/conftest.py` provides a Flask test client and separate in-memory
SQLite database, with cleanup between test cases. Normal application databases
are not used by these fixtures. The existing root `make test` target installs
dependencies, runs Pytest, and invokes the repository's test-database cleanup
routine. **Caution:** that cleanup also targets the configured PostgreSQL test
database. Ensure `TEST_DATABASE_URL` does not point to data you need to retain.

## Coverage locations

| Behavior | Test module |
| --- | --- |
| Authentication | `app/auth/tests/test_auth.py` |
| Business isolation / access permissions | `app/businesses/tests/`, `app/common/rbac/tests/`, `app/common/tests/test_tenant.py` |
| Customers | `app/customers/tests/test_customers.py` |
| WhatsApp verification, signatures, inbound processing and duplicate deliveries | `app/whatsapp/tests/test_webhook.py` |
| Conversations | `app/conversations/tests/` |
| Outbound WhatsApp messages and HTTP-provider failures | `app/messages/tests/test_messages.py` |
| Leads | `app/leads/tests/test_leads.py` |
| Bookings | `app/bookings/tests/test_bookings.py` |
| Payments | `app/payments/tests/test_payments.py` |
| Automation engine | `app/automations/tests/test_engine.py` |
| AI provider failures and suggestions | `app/ai/tests/test_reply_suggestions.py` |

Tests exercising external systems must replace those boundaries with fakes or
`monkeypatch` (e.g. `urlopen` for WhatsApp sending, and the AI provider for
suggestions). The webhook tests send signed payloads to Flask's local test
client: they do **not** call Meta or any other external service.

Run only the WhatsApp webhook checks:

```bash
cd backend
python -m pytest app/whatsapp/tests/test_webhook.py -v
```

Do not rely solely on a passing targeted test file: run the full suite before
merging and investigate unrelated failures separately.