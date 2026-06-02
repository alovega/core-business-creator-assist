from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from itertools import cycle

from flask import current_app

from app.whatsapp.models import WhatsAppIntegration
from app.whatsapp.validators import now


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
