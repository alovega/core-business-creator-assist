# API reference (OpenAPI / Swagger UI)

The backend now serves an OpenAPI 3.1 specification **for its existing Flask endpoints**. No business logic or database tables are added by this feature.

| URL (while the API is running) | Purpose |
| --- | --- |
| `http://127.0.0.1:5000/api/docs` | Interactive Swagger UI / Try it out |
| `http://127.0.0.1:5000/api/openapi.json` | OpenAPI JSON; import into Postman, Insomnia, Redoc, or a frontend code generator |

The Swagger UI loads its CSS/JS from jsDelivr (pinned to the major version of `swagger-ui-dist@5`), so the browser needs network access to that CDN. The JSON reference is served entirely by Flask and works without the CDN. Documentation routes are public **by design**; they do not expose real keys, credentials, or customer data.

## How frontend developers authenticate

1. `POST /api/auth/register` or `POST /api/auth/login` with JSON credentials; take the `access_token` from the response.
2. Choose a business: inspect `GET /api/businesses` or create one with `POST /api/businesses`. `POST /api/businesses/switch` changes your active workspace and returns a fresh `access_token`.
3. In Swagger UI click **Authorize**, paste **only** the token (Swagger UI constructs `Authorization: Bearer <token>`). In app code send `Authorization: Bearer <token>` on every secured operation.
4. For a business-specific request, optionally send `X-Business-Id: <business_id>`. The selected business must have an active membership. Selection uses the explicit header first, then session, JWT business claim, user's current business, then a single-member fallback. For URLs containing `/api/businesses/{business_id}`, membership is resolved against the URL ID instead.
5. Authenticated routes may also require a specific permission (for example `manage_bookings` or `view_customers`) as shown under each OpenAPI operation. Business settings updates require `manage_business_settings` and owner-only keys remain restricted.

JWTs expire and can be revoked by logging out. After business creation or a switch, replace the saved JWT with the new one. Client applications should clear the token and return to login on `401`; handle `403` as an access/permission problem. Do not embed signing secrets or real access tokens in documentation or source control.

### Example: login, then list customers

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"alex@example.com","password":"<your-password>"}'

curl 'http://127.0.0.1:5000/api/customers?page=1&per_page=20' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Business-Id: 1'
```

All names, numbers, dates, and IDs in the OpenAPI examples are **illustrative**. Use IDs returned by your own API; do not assume they exist in any deployed database.

## Response format and special cases

JSON `/api/` responses are standardized by `app/common/responses.py` without removing legacy keys:

```json
{
  "success": true,
  "message": "Success",
  "data": { "customer": { "id": 10, "business_id": 1 } },
  "error": null,
  "code": null,
  "details": null,
  "customer": { "id": 10, "business_id": 1 }
}
```

For legacy JSON routes, `data` contains their original JSON response, and the original top-level properties remain for compatibility. Errors use `success: false`, a textual `message`, an error `code`, and optional `details` / `errors` from validation. `DELETE` endpoints that respond with `204` have **no body**; `GET /api/media/{message_id}` returns binary media; `GET /api/whatsapp/webhook` echoes plaintext challenge. These do not use the JSON envelope. Some operations can return additional errors (for example WhatsApp provider failure `502` or AI provider failure `503`), even if the common error responses are not exhaustive.

Payment `amount` values are **strings** on responses to avoid floating-point rounding issues. Booking dates and polling cursors use ISO-8601 timestamps; the dashboard accepts ISO-8601 date or datetime filters. Customer list/search pagination returns a `pagination` object.

### WhatsApp webhooks are different from frontend JWT requests

- `GET /api/whatsapp/webhook` uses `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`. The token is checked against the configured `WHATSAPP_VERIFY_TOKEN`; a valid call returns the unmodified challenge string (Flask uses its default `text/html` response type).
- `POST /api/whatsapp/webhook` accepts Meta's event JSON and validates the required `X-Hub-Signature-256` header as `sha256=<hex HMAC-SHA256 of **raw request bytes** with META_APP_SECRET>`. It is not protected by a bearer JWT. Do not generate a signature from re-serialized JSON.
- The sample phone IDs and webhook message IDs are placeholders, not actual Meta credentials.

## Keeping documentation accurate

The checked-in specification is **generated** at `backend/app/api_docs/openapi.json`. To make changes:

1. Update the actual route/validators/models first.
2. Update curated `SAMPLES`, `BODY`, `QUERY`, `REQUIRED_FIELDS`, `ENUMS` or special cases in `backend/scripts/generate_openapi.py` when request/response behavior changes. The script reads `@*_bp.get/post/patch/delete/route` decorators from `backend/app/*/routes.py` without starting Flask or connecting to services.
3. From the repository root, run `make docs` to regenerate the JSON.
4. Run `make docs-check` before opening a PR. It regenerates in memory and fails if the committed file is stale; it also verifies route coverage, examples, authentication, and webhook behavior. The tests are also discovered by the existing backend pytest suite (`app/api_docs/tests/`).
5. In the PR description, include the documentation changes alongside any API-contract change. Review manually if the route remains the same but the payload/permission changes, because no static generator can infer every validator or response shape.

No migration, environment-variable addition, or new Python runtime dependency is required for this feature.