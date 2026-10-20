from datetime import datetime, timedelta

from pony.orm import commit, db_session

from app.businesses.models import Business
from app.conversations.models import Conversation
from app.messages.models import Message
from app.testing.helpers import auth_headers
from app.users.models import User


def test_polling_returns_changed_conversation_and_unread_count(owner_client):
    client, token = owner_client
    with db_session:
        business = User.get(email="owner@example.com").current_business
        cursor = datetime.utcnow()
        conversation = Conversation(
            business=business,
            customer_id=42,
            channel="whatsapp",
            updated_at=cursor + timedelta(seconds=1),
        )
        Message(
            business=business,
            conversation=conversation,
            customer_id=42,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body="New message",
            created_at=cursor + timedelta(seconds=1),
        )
        conversation.last_message_at = conversation.updated_at
        commit()
        conversation_id = conversation.id

    response = client.get(
        f"/api/conversations/updates?since={cursor.isoformat()}Z",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["id"] for item in payload["conversations"]] == [conversation_id]
    assert payload["conversations"][0]["unread_count"] == 1
    assert payload["since"].endswith("Z")

    response = client.get(
        f"/api/conversations/{conversation_id}/messages/updates?since={cursor.isoformat()}Z",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    assert [item["body"] for item in response.get_json()["messages"]] == [
        "New message"
    ]


def test_polling_enforces_business_isolation(owner_client):
    client, token = owner_client
    with db_session:
        other_business = Business(
            name="Other Corp",
            slug="other-corp",
            phone_number="+10000000000",
            industry="retail",
        )
        conversation = Conversation(
            business=other_business,
            customer_id=99,
            channel="whatsapp",
        )
        commit()
        conversation_id = conversation.id

    response = client.get(
        f"/api/conversations/{conversation_id}/messages/updates",
        headers=auth_headers(token),
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Conversation not found"


def test_polling_rejects_invalid_cursor(owner_client):
    client, token = owner_client

    response = client.get(
        "/api/conversations/updates?since=not-a-timestamp",
        headers=auth_headers(token),
    )

    assert response.status_code == 400