# File & Media Handling — Change guide

## Files

- NEW `backend/app/media/services.py`: validates bytes and MIME, retrieves Meta media with a bearer token, private local/S3 storage, tenant-scoped reads.
- NEW `backend/app/media/routes.py`: JWT/RBAC-protected `GET /api/media/<message_id>`.
- NEW `backend/app/whatsapp/routes.py`: verified GET/POST `/api/whatsapp/webhook` with tenant lookup via `Business.settings_json.whatsapp_phone_number_id`.
- NEW `backend/app/migrations/versions/1791900000_private_message_media.py`: additive message columns.
- NEW `backend/app/media/tests/test_media_service.py`: storage/validation unit tests.
- UPDATED `backend/app/messages/models.py`: media metadata serialization, safe internal download path.
- UPDATED `backend/app/__init__.py`: imports and registers webhook/media routes.
- UPDATED `backend/app/config.py`: `MEDIA_MAX_BYTES`.
- UPDATED `backend/requirements.txt`: optional S3 driver boto3 (installed by requirements).
- UPDATED `backend/.env.example`: media limit.
- UPDATED `docker-compose.yml`: persistent private media volume `/media`.
- UPDATED `.gitignore`: exclude local uploaded files.

## Setup

1. `pip install -r backend/requirements.txt` (or rebuild Docker container).
2. Set `STORAGE_BACKEND=local` and use a non-public server path for `STORAGE_LOCAL_PATH`; in Docker Compose `/media` is wired automatically.
3. Set `MEDIA_MAX_BYTES=16777216` (16 MiB example), `META_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`.
4. In each tenant's **owner-only** `Business.settings_json`, provision a unique Meta `whatsapp_phone_number_id` value. Ensure mapping uniqueness in provisioning logic; the webhook rejects ambiguous mappings. The current general business settings may be too widely readable: do not store access tokens there.
5. In Meta developer console set callback `/api/whatsapp/webhook`, verify token, and subscribe to `messages` events.
6. Start/restart API; project migration runner will apply migration when `RUN_MIGRATIONS=true`.
7. Test the download with `Authorization: Bearer <JWT>` and your existing business-selection context; private media returns `media_download_path` in the essage payload.

## Known implementation limitations / production follow-up

- The project has no existing multi-business WhatsApp credential/phone-number registration model. The code uses the global Meta token and tenant mapping from settings_json`; full multi-tenant credential management must precede broader rollout.
- Incoming webhook downloads are synchronous. For production, enqueue a Celery job, acknowledge Meta immediately, retry transient failures, and implement an dempotent uniqueness constraint `(business, provider_message_id)` before handling concurrent deliveries at scale.
- Outbound media still relies on the old `media_url` sending path; for private outgoing files implement WhatsApp `/media` upload and send by Meta media `id`, ot by a protected download URL.
- File signatures are a first-pass safeguard, not malware detection. Add stronger format parsing and antivirus scanning, especially for PDFs and Office ocuments, before allowing inline preview.
- `media_status='rejected'` represents all ingestion errors, including transient errors; change to retryable `failed` status in worker integration.
- Authenticated downloads work with Authorization headers, not unauthenticated `<img src>` references. Frontend should fetch blobs with auth, or use hort-lived signed links scoped to the tenant.
- Enforce encrypted backups, retention/deletion lifecycle, access auditing, and private S3 bucket policy/block-public-access in infrastructure.
- Validate webhook delivery and regressions against the running DB; this environment did not have Flask installed for test execution.