from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WhatsAppWebhookEventType(StrEnum):
    INCOMING_MESSAGE = "incoming_message"
    MESSAGE_STATUS_UPDATE = "message_status_update"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ParsedIncomingMessage:
    phone_number_id: str
    provider_message_id: str
    customer_phone_number: str
    profile_name: str | None
    message_body: str | None
    raw_message: dict


@dataclass(frozen=True)
class ParsedMessageStatusUpdate:
    phone_number_id: str
    provider_message_id: str
    status: str
    metadata: dict


def _first_change(payload: dict) -> dict | None:
    entries = payload.get("entry")
    if not isinstance(entries, list) or not entries:
        return None
    first_entry = entries[0]
    if not isinstance(first_entry, dict):
        return None
    changes = first_entry.get("changes")
    if not isinstance(changes, list) or not changes:
        return None
    first_change = changes[0]
    if not isinstance(first_change, dict):
        return None
    value = first_change.get("value")
    return value if isinstance(value, dict) else None


def _phone_number_id(value: dict) -> str | None:
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        return None
    phone_number_id = metadata.get("phone_number_id")
    if not isinstance(phone_number_id, str) or not phone_number_id.strip():
        return None
    return phone_number_id.strip()


def detect_event_type(payload: dict) -> WhatsAppWebhookEventType:
    value = _first_change(payload)
    if value is None:
        return WhatsAppWebhookEventType.UNSUPPORTED
    if isinstance(value.get("messages"), list) and value["messages"]:
        return WhatsAppWebhookEventType.INCOMING_MESSAGE
    if isinstance(value.get("statuses"), list) and value["statuses"]:
        return WhatsAppWebhookEventType.MESSAGE_STATUS_UPDATE
    return WhatsAppWebhookEventType.UNSUPPORTED


def parse_incoming_message(payload: dict) -> ParsedIncomingMessage | None:
    value = _first_change(payload)
    if value is None:
        return None
    phone_number_id = _phone_number_id(value)
    if phone_number_id is None:
        return None
    contacts = value.get("contacts")
    messages = value.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    message = messages[0]
    if not isinstance(message, dict):
        return None
    provider_message_id = message.get("id")
    customer_phone = message.get("from")
    if not isinstance(provider_message_id, str) or not provider_message_id.strip():
        return None
    if not isinstance(customer_phone, str) or not customer_phone.strip():
        return None
    profile_name = None
    if isinstance(contacts, list) and contacts and isinstance(contacts[0], dict):
        profile = contacts[0].get("profile")
        if isinstance(profile, dict):
            raw_name = profile.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                profile_name = raw_name.strip()
    message_body = None
    if message.get("type") == "text":
        text_payload = message.get("text")
        if isinstance(text_payload, dict):
            body = text_payload.get("body")
            if isinstance(body, str) and body.strip():
                message_body = body.strip()
    return ParsedIncomingMessage(
        phone_number_id=phone_number_id,
        provider_message_id=provider_message_id.strip(),
        customer_phone_number=customer_phone.strip(),
        profile_name=profile_name,
        message_body=message_body,
        raw_message=message,
    )


def parse_message_status_update(payload: dict) -> ParsedMessageStatusUpdate | None:
    value = _first_change(payload)
    if value is None:
        return None
    phone_number_id = _phone_number_id(value)
    if phone_number_id is None:
        return None
    statuses = value.get("statuses")
    if not isinstance(statuses, list) or not statuses:
        return None
    status_payload = statuses[0]
    if not isinstance(status_payload, dict):
        return None
    provider_message_id = status_payload.get("id")
    status = status_payload.get("status")
    if not isinstance(provider_message_id, str) or not provider_message_id.strip():
        return None
    if not isinstance(status, str) or not status.strip():
        return None
    metadata = {
        "recipient_id": status_payload.get("recipient_id"),
        "timestamp": status_payload.get("timestamp"),
        "errors": status_payload.get("errors"),
        "conversation": status_payload.get("conversation"),
        "pricing": status_payload.get("pricing"),
    }
    return ParsedMessageStatusUpdate(
        phone_number_id=phone_number_id,
        provider_message_id=provider_message_id.strip(),
        status=status.strip().lower(),
        metadata=metadata,
    )
