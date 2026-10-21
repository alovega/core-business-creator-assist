"""WhatsApp webhook integration tests; all requests are local Flask test-client calls."""
import hashlib
import hmac
import json

import pytest
from pony.orm import db_session, flush

from app.businesses.models import Business
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.messages.models import Message


@pytest.fixture
def webhook_client(client):
    client.application.config.update(
        WHATSAPP_VERIFY_TOKEN="verification-token",
        META_APP_SECRET="test-app-secret",
    )
    return client


def _signed_post(client, payload, *, secret="test-app-secret"):
    """Sign the exact bytes sent, matching Meta's X-Hub-Signature-256 protocol."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/api/whatsapp/webhook",
        data=raw,
        content_type="application/json",
        headers={"X-Hub-Signature-256": f"sha256={signature}"},
    )


def _event(phone_id="phone-1", message_id="wamid.inbound-1"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{
            "field": "messages",
            "value": {
                "metadata": {"phone_number_id": phone_id},
                "contacts": [{"wa_id": "15551234567", "profile": {"name": "Alex"}}],
                "messages": [{
                    "from": "15551234567",
                    "id": message_id,
                    "type": "text",
                    "text": {"body": "Hi from WhatsApp"},
                }],
            },
        }]}],
    }


def test_webhook_verification_accepts_matching_token(webhook_client):
    response = webhook_client.get("/api/whatsapp/webhook", query_string={
        "hub.mode": "subscribe", "hub.verify_token": "verification-token",
        "hub.challenge": "check-123",
    })
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "check-123"


@pytest.mark.parametrize("mode,token", [
    ("subscribe", "incorrect"),
    ("unsubscribe", "verification-token"),
    ("subscribe", ""),
])
def test_webhook_verification_rejects_invalid_requests(webhook_client, mode, token):
    response = webhook_client.get("/api/whatsapp/webhook", query_string={
        "hub.mode": mode, "hub.verify_token": token, "hub.challenge": "secret",
    })
    assert response.status_code == 403
    assert response.get_data(as_text=True) != "secret"


def test_webhook_rejects_missing_or_incorrect_signature(webhook_client):
    payload = _event()
    missing = webhook_client.post("/api/whatsapp/webhook", json=payload)
    incorrect = _signed_post(webhook_client, payload, secret="wrong-secret")
    assert missing.status_code == 403
    assert incorrect.status_code == 403
    with db_session:
        assert Message.select().count() == 0


def test_webhook_rejects_non_whatsapp_payload(webhook_client):
    response = _signed_post(webhook_client, {"object": "unexpected", "entry": []})
    assert response.status_code == 400


def test_webhook_processes_inbound_message_once_and_keeps_tenant_boundary(
    webhook_client,
):
    # Directly seed separate tenants; webhook routing must use the phone ID,
    # never a tenant ID supplied by the sender.
    with db_session:
        destination = Business(
            name="Destination", slug="webhook-destination",
            settings_json={"whatsapp_phone_number_id": "phone-1"},
        )
        unrelated = Business(
            name="Unrelated", slug="webhook-unrelated",
            settings_json={"whatsapp_phone_number_id": "phone-2"},
        )
        flush()  # Ensure IDs are assigned for later comparison
        destination_id, unrelated_id = destination.id, unrelated.id

    event = _event()
    first = _signed_post(webhook_client, event)
    retry = _signed_post(webhook_client, event)
    assert first.status_code == 200
    assert retry.status_code == 200
    assert first.get_json()["received"] is True

    with db_session:
        assert Message.select().count() == 1
        assert Customer.select().count() == 1
        assert Conversation.select().count() == 1
        message = Message.select().first()
        assert message.business.id == destination_id
        assert message.business.id != unrelated_id
        assert message.direction == "incoming"
        assert message.body == "Hi from WhatsApp"
        assert message.status == "received"
        assert message.conversation.unread_count == 1


def test_webhook_does_not_assign_unmapped_phone_id_to_any_tenant(webhook_client):
    with db_session:
        Business(name="Tenant", slug="webhook-tenant",
                 settings_json={"whatsapp_phone_number_id": "configured-phone"})
    response = _signed_post(webhook_client, _event(phone_id="unknown-phone"))
    assert response.status_code == 200
    with db_session:
        assert Message.select().count() == 0
        assert Customer.select().count() == 0


def test_webhook_fails_closed_if_phone_id_matches_multiple_tenants(webhook_client):
    with db_session:
        for index in range(2):
            Business(name=f"Tenant {index}", slug=f"ambiguous-{index}",
                     settings_json={"whatsapp_phone_number_id": "shared-phone"})
    response = _signed_post(webhook_client, _event(phone_id="shared-phone"))
    assert response.status_code == 200
    with db_session:
        assert Message.select().count() == 0