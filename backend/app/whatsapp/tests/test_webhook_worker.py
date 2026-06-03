from pony.orm import db_session

from app.conversations.models import Conversation
from app.customers.models import Customer
from app.messages.models import Message
from app.testing.helpers import auth_headers, create_business, register_user
from app.users.models import User
from app.whatsapp.services import process_webhook_payload
from app.whatsapp.webhook_parser import (
    WhatsAppWebhookEventType,
    detect_event_type,
    parse_incoming_message,
    parse_message_status_update,
)


def _create_integration(client, token, **overrides):
    payload = {
        "phone_number_id": "pnid-1",
        "whatsapp_business_account_id": "waba-1",
        "display_phone_number": "+12025550000",
        "access_token": "meta-token",
        "verify_token": "verify-123",
        "app_secret": "meta-secret",
    }
    payload.update(overrides)
    response = client.post(
        "/api/whatsapp/integration",
        json=payload,
        headers=auth_headers(token),
    )
    assert response.status_code == 201
    return payload


def _incoming_payload(*, phone_number_id: str = "pnid-1", message_id: str = "wamid.in.1", from_phone: str = "12025550123"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "contacts": [
                                {"wa_id": from_phone, "profile": {"name": "Alice Sender"}}
                            ],
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": from_phone,
                                    "type": "text",
                                    "text": {"body": "Hello bot"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def _status_payload(*, phone_number_id: str = "pnid-1", message_id: str = "wamid.in.1", status: str = "delivered"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "statuses": [
                                {
                                    "id": message_id,
                                    "status": status,
                                    "timestamp": "1717000000",
                                    "recipient_id": "12025550123",
                                    "errors": [{"code": 131026, "title": "Temporary issue"}],
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


class TestWebhookParser:
    def test_detects_incoming_and_status_events(self):
        assert detect_event_type(_incoming_payload()) == WhatsAppWebhookEventType.INCOMING_MESSAGE
        assert (
            detect_event_type(_status_payload())
            == WhatsAppWebhookEventType.MESSAGE_STATUS_UPDATE
        )
        assert detect_event_type({"entry": []}) == WhatsAppWebhookEventType.UNSUPPORTED

    def test_parses_incoming_payload(self):
        parsed = parse_incoming_message(_incoming_payload())
        assert parsed is not None
        assert parsed.phone_number_id == "pnid-1"
        assert parsed.provider_message_id == "wamid.in.1"
        assert parsed.customer_phone_number == "12025550123"
        assert parsed.profile_name == "Alice Sender"
        assert parsed.message_body == "Hello bot"

    def test_parses_status_payload(self):
        parsed = parse_message_status_update(_status_payload(status="failed"))
        assert parsed is not None
        assert parsed.provider_message_id == "wamid.in.1"
        assert parsed.status == "failed"
        assert parsed.metadata["recipient_id"] == "12025550123"


class TestWebhookWorker:
    def test_processes_incoming_message_and_creates_records(self, client, app, owner_client):
        _, token = owner_client
        _create_integration(client, token)

        result = process_webhook_payload(_incoming_payload())
        assert result["ok"] is True
        assert result["message_created"] is True

        with app.app_context():
            with db_session:
                business = User.get(email="owner@example.com").current_business
                customer = Customer.get(
                    business=business, normalized_phone_number="+12025550123"
                )
                assert customer is not None
                conversation = Conversation.get(
                    business=business, customer=customer, channel="whatsapp"
                )
                assert conversation is not None
                assert conversation.unread_count == 1
                message = Message.get(
                    business=business, provider_message_id="wamid.in.1"
                )
                assert message is not None
                assert message.status == "received"

    def test_incoming_webhook_is_idempotent(self, client, app, owner_client):
        _, token = owner_client
        _create_integration(client, token)
        payload = _incoming_payload()
        first = process_webhook_payload(payload)
        second = process_webhook_payload(payload)
        assert first["ok"] is True
        assert second["ok"] is True
        assert second["message_created"] is False

        with app.app_context():
            with db_session:
                business = User.get(email="owner@example.com").current_business
                assert len([c for c in Customer.select() if c.business == business]) == 1
                assert (
                    len([c for c in Conversation.select() if c.business == business]) == 1
                )
                assert len([m for m in Message.select() if m.business == business]) == 1

    def test_processes_status_update(self, client, app, owner_client):
        _, token = owner_client
        _create_integration(client, token)
        process_webhook_payload(_incoming_payload())

        result = process_webhook_payload(_status_payload(status="delivered"))
        assert result["ok"] is True
        assert result["status"] == "delivered"

        with app.app_context():
            with db_session:
                business = User.get(email="owner@example.com").current_business
                message = Message.get(
                    business=business, provider_message_id="wamid.in.1"
                )
                assert message is not None
                assert message.status == "delivered"
                assert message.delivered_at is not None

    def test_missing_integration_is_handled_safely(self, app):
        result = process_webhook_payload(_incoming_payload(phone_number_id="missing-pnid"))
        assert result["ok"] is False
        assert result["reason"] == "integration_not_found"
        with app.app_context():
            with db_session:
                assert Customer.select().count() == 0
                assert Conversation.select().count() == 0
                assert Message.select().count() == 0

    def test_unsupported_event_is_logged_without_crashing(self):
        result = process_webhook_payload({"entry": [{"changes": [{"value": {"foo": "bar"}}]}]})
        assert result["ok"] is False
        assert result["event_type"] == WhatsAppWebhookEventType.UNSUPPORTED.value

    def test_invalid_payload_is_non_retryable(self):
        result = process_webhook_payload({"entry": "bad-shape"})
        assert result["ok"] is False
        assert result["retryable"] is False

    def test_tenant_isolation_for_provider_message_id(self, client, app, owner_client):
        _, owner_token = owner_client
        _create_integration(client, owner_token, phone_number_id="pnid-owner")

        outsider = register_user(client, email="outside-webhook@example.com")
        outsider_token = outsider.get_json()["access_token"]
        create_business(client, outsider_token, name="Other Co")
        _create_integration(client, outsider_token, phone_number_id="pnid-other")

        owner_result = process_webhook_payload(
            _incoming_payload(phone_number_id="pnid-owner", message_id="wamid.same.1")
        )
        other_result = process_webhook_payload(
            _incoming_payload(phone_number_id="pnid-other", message_id="wamid.same.1")
        )
        assert owner_result["ok"] is True
        assert other_result["ok"] is True
        assert owner_result["business_id"] != other_result["business_id"]

        with app.app_context():
            with db_session:
                owner_business = User.get(email="owner@example.com").current_business
                other_business = User.get(email="outside-webhook@example.com").current_business
                owner_message = Message.get(
                    business=owner_business, provider_message_id="wamid.same.1"
                )
                other_message = Message.get(
                    business=other_business, provider_message_id="wamid.same.1"
                )
                assert owner_message is not None
                assert other_message is not None
                assert owner_message.business.id != other_message.business.id
