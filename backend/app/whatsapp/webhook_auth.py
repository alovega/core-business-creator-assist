from __future__ import annotations

import hashlib
import hmac

from flask import current_app
from pony.orm import db_session

from app.whatsapp.models import WhatsAppIntegration


def _configured_verify_token() -> str:
    return (current_app.config.get("WHATSAPP_VERIFY_TOKEN") or "").strip()


def _configured_app_secret() -> str:
    return (current_app.config.get("META_APP_SECRET") or "").strip()


def is_valid_verify_token(token: str) -> bool:
    """Return True if token matches app config or any stored integration."""
    candidate = (token or "").strip()
    if not candidate:
        return False
    if candidate == _configured_verify_token():
        return True

    @db_session
    def _matches_integration() -> bool:
        return WhatsAppIntegration.get(verify_token=candidate) is not None

    return _matches_integration()


def verify_webhook_signature(*, raw_body: bytes, signature_header: str | None) -> bool:
    """Validate Meta X-Hub-Signature-256 header."""
    app_secret = _configured_app_secret()
    if not app_secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = signature_header.removeprefix("sha256=")
    digest = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)
