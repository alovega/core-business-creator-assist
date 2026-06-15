from __future__ import annotations

import hashlib
import hmac
import json

import pytest


def _sign_payload(payload: dict, *, secret: str) -> tuple[bytes, str]:
    raw = json.dumps(payload).encode()
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, f"sha256={digest}"


@pytest.fixture
def webhook_secrets(app):
    app.config["WHATSAPP_VERIFY_TOKEN"] = "verify-123"
    app.config["META_APP_SECRET"] = "meta-app-secret"
    return app


class TestWhatsAppWebhookRoutes:
    def test_get_verification_returns_challenge(self, client, webhook_secrets):
        response = client.get(
            "/api/whatsapp/webhook",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-123",
                "hub.challenge": "challenge-token-42",
            },
        )
        assert response.status_code == 200
        assert response.data.decode() == "challenge-token-42"

    def test_get_verification_rejects_invalid_token(self, client, webhook_secrets):
        response = client.get(
            "/api/whatsapp/webhook",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "challenge-token-42",
            },
        )
        assert response.status_code == 403

    def test_post_webhook_enqueues_payload(self, client, webhook_secrets, monkeypatch):
        enqueued: list[dict] = []

        def _delay(payload):
            enqueued.append(payload)

        monkeypatch.setattr(
            "app.whatsapp.routes.process_whatsapp_webhook.delay",
            _delay,
        )
        payload = {"entry": [{"id": "waba", "changes": []}]}
        raw, signature = _sign_payload(payload, secret="meta-app-secret")
        response = client.post(
            "/api/whatsapp/webhook",
            data=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )
        assert response.status_code == 200
        assert response.get_json() == {"ok": True}
        assert enqueued == [payload]

    def test_post_webhook_rejects_invalid_signature(self, client, webhook_secrets, monkeypatch):
        monkeypatch.setattr(
            "app.whatsapp.routes.process_whatsapp_webhook.delay",
            lambda _payload: None,
        )
        payload = {"entry": []}
        raw, _ = _sign_payload(payload, secret="meta-app-secret")
        response = client.post(
            "/api/whatsapp/webhook",
            data=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=deadbeef",
            },
        )
        assert response.status_code == 403

    def test_post_webhook_rejects_invalid_json(self, client, webhook_secrets):
        raw = b"not-json"
        digest = hmac.new(b"meta-app-secret", raw, hashlib.sha256).hexdigest()
        response = client.post(
            "/api/whatsapp/webhook",
            data=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={digest}",
            },
        )
        assert response.status_code == 400
