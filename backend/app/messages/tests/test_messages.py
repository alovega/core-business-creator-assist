from pony.orm import commit, db_session

from app.businesses.models import Business
from app.conversations.models import Conversation
from app.messages import services as message_services
from app.messages.models import Message
from app.testing.helpers import auth_headers


def create_conversation(business_id: int) -> int:
    with db_session:
        conversation = Conversation(
            business=Business.get(id=business_id),
            customer_id=42,
            channel="whatsapp",
            contact_phone_number="15551234567",
        )
        commit()
        return conversation.id


def test_send_and_get_whatsapp_message(owner_client, monkeypatch):
    client, token = owner_client
    client.application.config.update(
        WHATSAPP_PHONE_NUMBER_ID="phone-id",
        WHATSAPP_ACCESS_TOKEN="access-token",
    )
    business_id = client.get(
        "/api/businesses/current", headers=auth_headers(token)
    ).get_json()["business"]["id"]
    conversation_id = create_conversation(business_id)

    class SuccessfulResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"messages": [{"id": "wamid.sent-123"}]}'

    monkeypatch.setattr(
        message_services,
        "urlopen",
        lambda *args, **kwargs: SuccessfulResponse(),
    )
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"body": "Hello from the team"},
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    sent = response.get_json()["message"]
    assert sent["status"] == "sent"
    assert sent["provider_message_id"] == "wamid.sent-123"
    assert sent["direction"] == "outgoing"

    response = client.get(
        f"/api/messages/{conversation_id}", headers=auth_headers(token)
    )
    assert response.status_code == 200
    assert response.get_json()["messages"][0]["body"] == "Hello from the team"

    with db_session:
        message = Message.get(provider_message_id="wamid.sent-123")
        assert message is not None
        assert message.conversation.last_message_at is not None


def test_failed_whatsapp_message_is_stored_as_failed(owner_client, monkeypatch):
    client, token = owner_client
    client.application.config.update(
        WHATSAPP_PHONE_NUMBER_ID="phone-id",
        WHATSAPP_ACCESS_TOKEN="access-token",
    )
    business_id = client.get(
        "/api/businesses/current", headers=auth_headers(token)
    ).get_json()["business"]["id"]
    conversation_id = create_conversation(business_id)

    def fail_send(*args, **kwargs):
        from urllib.error import URLError

        raise URLError("provider unavailable")

    monkeypatch.setattr(message_services, "urlopen", fail_send)
    response = client.post(
        f"/api/messages/{conversation_id}",
        json={"body": "This will fail"},
        headers=auth_headers(token),
    )

    assert response.status_code == 502
    assert response.get_json()["message"]["status"] == "failed"
    with db_session:
        assert Message.select().count() == 1
        assert Message.select().first().status == "failed"
