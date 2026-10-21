# File & Media Handling — Change guide
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