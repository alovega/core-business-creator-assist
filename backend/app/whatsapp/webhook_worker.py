from __future__ import annotations

import logging

from app.extensions import celery
from app.whatsapp.services import process_webhook_payload

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    name="app.whatsapp.webhook_worker.process_whatsapp_webhook",
    max_retries=3,
    default_retry_delay=10,
)
def process_whatsapp_webhook(self, payload: dict):
    """Process queued WhatsApp webhook payloads in background."""
    try:
        result = process_webhook_payload(payload or {})
    except Exception as exc:
        logger.exception("Failed to process WhatsApp webhook payload")
        raise self.retry() from exc

    if not result.get("ok") and result.get("retryable"):
        raise self.retry()

    return result
