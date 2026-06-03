from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from itertools import cycle

from flask import current_app
from pony.orm import commit, db_session

from app.conversations.services import find_or_create_conversation, mark_inbound_activity
from app.customers.services import find_or_create_whatsapp_customer, normalize_phone_number
from app.messages.services import (
    create_inbound_whatsapp_message,
    find_by_provider_message_id,
    update_whatsapp_message_status,
)
from app.whatsapp.models import WhatsAppIntegration
from app.whatsapp.webhook_parser import (
    WhatsAppWebhookEventType,
    detect_event_type,
    parse_incoming_message,
    parse_message_status_update,
)
from app.whatsapp.validators import now

logger = logging.getLogger(__name__)


def _secret_key_material() -> bytes:
    material = (current_app.config.get("SECRET_KEY") or "").encode()
    if not material:
        raise RuntimeError("SECRET_KEY is required for WhatsApp secret encryption")
    return hashlib.sha256(material).digest()


def encrypt_secret(value: str) -> str:
    nonce = secrets.token_bytes(16)
    plaintext = value.encode()
    key = hashlib.sha256(_secret_key_material() + nonce).digest()
    encrypted = bytes(a ^ b for a, b in zip(plaintext, cycle(key)))
    signature = hmac.new(_secret_key_material(), nonce + encrypted, hashlib.sha256).digest()
    payload = nonce + encrypted + signature
    return base64.urlsafe_b64encode(payload).decode()


def decrypt_secret(value: str) -> str:
    payload = base64.urlsafe_b64decode(value.encode())
    nonce = payload[:16]
    signature = payload[-32:]
    encrypted = payload[16:-32]
    expected = hmac.new(_secret_key_material(), nonce + encrypted, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise RuntimeError("Encrypted secret integrity check failed")
    key = hashlib.sha256(_secret_key_material() + nonce).digest()
    plaintext = bytes(a ^ b for a, b in zip(encrypted, cycle(key)))
    return plaintext.decode()


def get_integration_for_business(business, *, phone_number_id: str | None = None):
    if phone_number_id:
        return WhatsAppIntegration.get(
            business=business,
            phone_number_id=phone_number_id.strip(),
            status="connected",
        )
    return WhatsAppIntegration.get(business=business, status="connected")


def create_or_update_integration(*, business, actor, data: dict):
    integration = WhatsAppIntegration.get(
        business=business,
        phone_number_id=data["phone_number_id"].strip(),
    )
    ts = now()
    if integration is None:
        integration = WhatsAppIntegration(
            business=business,
            phone_number_id=data["phone_number_id"].strip(),
            whatsapp_business_account_id=data["whatsapp_business_account_id"].strip(),
            display_phone_number=data["display_phone_number"].strip(),
            access_token_encrypted=encrypt_secret(data["access_token"].strip()),
            verify_token=data["verify_token"].strip(),
            app_secret=encrypt_secret(data["app_secret"].strip()),
            status="connected",
            connected_at=ts,
            created_by=actor,
            updated_by=actor,
            created_at=ts,
            updated_at=ts,
        )
        return integration, True

    if "whatsapp_business_account_id" in data:
        integration.whatsapp_business_account_id = data["whatsapp_business_account_id"].strip()
    if "display_phone_number" in data:
        integration.display_phone_number = data["display_phone_number"].strip()
    if "access_token" in data:
        integration.access_token_encrypted = encrypt_secret(data["access_token"].strip())
    if "verify_token" in data:
        integration.verify_token = data["verify_token"].strip()
    if "app_secret" in data:
        integration.app_secret = encrypt_secret(data["app_secret"].strip())
    integration.status = "connected"
    integration.disconnected_at = None
    integration.connected_at = integration.connected_at or ts
    integration.updated_by = actor
    integration.updated_at = ts
    return integration, False


def disconnect_integration(*, integration, actor):
    integration.status = "disconnected"
    integration.disconnected_at = now()
    integration.updated_by = actor
    integration.updated_at = now()


def trigger_automation_checks(*, business_id: int, conversation_id: int, message_id: int) -> None:
    # Placeholder for automation hook integration.
    logger.debug(
        "Automation checks triggered",
        extra={
            "business_id": business_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
        },
    )


def trigger_realtime_inbox_update(*, business_id: int, conversation_id: int) -> None:
    # Placeholder for realtime notifications (e.g. websocket/pubsub).
    logger.debug(
        "Realtime inbox update triggered",
        extra={"business_id": business_id, "conversation_id": conversation_id},
    )


@db_session
def process_incoming_message_event(payload: dict) -> dict:
    parsed = parse_incoming_message(payload)
    if parsed is None:
        return {"ok": False, "reason": "invalid_incoming_payload", "retryable": False}

    integration = WhatsAppIntegration.get(
        phone_number_id=parsed.phone_number_id,
        status="connected",
    )
    if integration is None:
        logger.warning(
            "WhatsApp integration not found for phone_number_id",
            extra={"phone_number_id": parsed.phone_number_id, "payload": payload},
        )
        return {"ok": False, "reason": "integration_not_found", "retryable": False}

    business = integration.business
    normalized_phone = normalize_phone_number(parsed.customer_phone_number)
    if not normalized_phone:
        return {"ok": False, "reason": "invalid_customer_phone", "retryable": False}

    customer, customer_created = find_or_create_whatsapp_customer(
        business=business,
        phone_number=parsed.customer_phone_number,
        profile_name=parsed.profile_name,
    )
    conversation, conversation_created = find_or_create_conversation(
        business=business,
        customer=customer,
        channel="whatsapp",
    )
    message, message_created = create_inbound_whatsapp_message(
        business=business,
        customer=customer,
        conversation=conversation,
        provider_message_id=parsed.provider_message_id,
        body=parsed.message_body,
        provider_payload={"raw_message": parsed.raw_message},
    )

    if message_created:
        mark_inbound_activity(conversation=conversation)
    commit()

    if message_created:
        trigger_automation_checks(
            business_id=business.id,
            conversation_id=conversation.id,
            message_id=message.id,
        )
        trigger_realtime_inbox_update(
            business_id=business.id,
            conversation_id=conversation.id,
        )

    logger.info(
        "Processed incoming WhatsApp webhook",
        extra={
            "business_id": business.id,
            "phone_number_id": parsed.phone_number_id,
            "provider_message_id": parsed.provider_message_id,
            "message_created": message_created,
        },
    )
    return {
        "ok": True,
        "event_type": WhatsAppWebhookEventType.INCOMING_MESSAGE.value,
        "business_id": business.id,
        "customer_id": customer.id,
        "conversation_id": conversation.id,
        "message_id": message.id,
        "customer_created": customer_created,
        "conversation_created": conversation_created,
        "message_created": message_created,
        "retryable": False,
    }


@db_session
def process_message_status_event(payload: dict) -> dict:
    parsed = parse_message_status_update(payload)
    if parsed is None:
        return {"ok": False, "reason": "invalid_status_payload", "retryable": False}

    integration = WhatsAppIntegration.get(
        phone_number_id=parsed.phone_number_id,
        status="connected",
    )
    if integration is None:
        logger.warning(
            "WhatsApp integration not found for status update",
            extra={"phone_number_id": parsed.phone_number_id, "payload": payload},
        )
        return {"ok": False, "reason": "integration_not_found", "retryable": False}

    message = find_by_provider_message_id(
        business=integration.business,
        provider_message_id=parsed.provider_message_id,
    )
    if message is None:
        logger.info(
            "WhatsApp status update did not match a message",
            extra={
                "business_id": integration.business.id,
                "provider_message_id": parsed.provider_message_id,
                "status": parsed.status,
            },
        )
        return {"ok": False, "reason": "message_not_found", "retryable": False}

    if parsed.status not in {"sent", "delivered", "read", "failed", "undeliverable"}:
        logger.info(
            "Unsupported WhatsApp message status",
            extra={
                "business_id": integration.business.id,
                "provider_message_id": parsed.provider_message_id,
                "status": parsed.status,
            },
        )
        return {"ok": False, "reason": "unsupported_status", "retryable": False}

    update_whatsapp_message_status(
        message=message,
        status=parsed.status,
        metadata=parsed.metadata,
    )
    commit()
    return {
        "ok": True,
        "event_type": WhatsAppWebhookEventType.MESSAGE_STATUS_UPDATE.value,
        "business_id": integration.business.id,
        "message_id": message.id,
        "status": parsed.status,
        "retryable": False,
    }


def process_webhook_payload(payload: dict) -> dict:
    event_type = detect_event_type(payload)
    if event_type is WhatsAppWebhookEventType.INCOMING_MESSAGE:
        return process_incoming_message_event(payload)
    if event_type is WhatsAppWebhookEventType.MESSAGE_STATUS_UPDATE:
        return process_message_status_event(payload)
    logger.info("Unsupported WhatsApp webhook event", extra={"payload": payload})
    return {
        "ok": False,
        "event_type": WhatsAppWebhookEventType.UNSUPPORTED.value,
        "reason": "unsupported_event",
        "retryable": False,
    }
