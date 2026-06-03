from __future__ import annotations

from datetime import UTC, datetime

from app.common.db_errors import is_unique_violation
from app.messages.models import Message


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def find_by_provider_message_id(*, business, provider_message_id: str):
    return Message.get(
        business=business,
        provider_message_id=provider_message_id,
    )


def create_inbound_whatsapp_message(
    *,
    business,
    customer,
    conversation,
    provider_message_id: str,
    body: str | None,
    provider_payload: dict,
    occurred_at: datetime | None = None,
):
    existing = find_by_provider_message_id(
        business=business,
        provider_message_id=provider_message_id,
    )
    if existing is not None:
        return existing, False

    timestamp = occurred_at or _utcnow_naive()
    try:
        message = Message(
            business=business,
            customer=customer,
            conversation=conversation,
            channel="whatsapp",
            direction="inbound",
            status="received",
            body=body,
            provider_message_id=provider_message_id,
            provider_payload=provider_payload,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return message, True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if not is_unique_violation(exc):
            raise
        existing = find_by_provider_message_id(
            business=business,
            provider_message_id=provider_message_id,
        )
        if existing is None:
            raise
        return existing, False


def update_whatsapp_message_status(
    *,
    message,
    status: str,
    metadata: dict | None = None,
):
    message.status = status
    merged_metadata = dict(message.provider_payload or {})
    if metadata:
        merged_metadata["status_metadata"] = metadata
    message.provider_payload = merged_metadata
    if status in {"delivered", "read"}:
        message.delivered_at = _utcnow_naive()
    if status in {"failed", "undeliverable"}:
        message.failed_at = _utcnow_naive()
        message.failure_reason = (metadata or {}).get("error_message")
    message.updated_at = _utcnow_naive()
    return message
