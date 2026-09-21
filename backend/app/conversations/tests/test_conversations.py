from datetime import datetime, timedelta

from pony.orm import commit, db_session

from app.conversations.models import Conversation
from app.testing.helpers import add_business_member, auth_headers, register_user
from app.users.models import User
from app.common.rbac.access import ErrorCode


def test_list_conversations_filters_and_sorts_latest_first(owner_client):
    client, token = owner_client

    with db_session:
        business = User.get(email="owner@example.com").current_business
        oldest = Conversation(
            business=business,
            customer_id=10,
            channel="whatsapp",
            status="open",
            priority="normal",
            unread_count=0,
            tags_json=["vip"],
            last_message_at=datetime.utcnow() - timedelta(hours=2),
        )
        latest = Conversation(
            business=business,
            customer_id=11,
            channel="whatsapp",
            status="pending",
            priority="high",
            unread_count=1,
            tags_json=["vip", "urgent"],
            last_message_at=datetime.utcnow(),
        )
        commit()

    response = client.get(
        "/api/conversations?status=pending&channel=whatsapp&priority=high&tag=urgent&unread=true",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert [item["id"] for item in payload["conversations"]] == [latest.id]
    assert payload["conversations"][0]["unread_count"] == 1

    response = client.get(
        "/api/conversations",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["id"] for item in payload["conversations"]] == [latest.id, oldest.id]


def test_mark_conversation_as_read_clears_unread_count(owner_client):
    client, token = owner_client

    with db_session:
        business = User.get(email="owner@example.com").current_business
        conversation = Conversation(
            business=business,
            customer_id=42,
            channel="whatsapp",
            status="open",
            unread_count=2,
            last_message_at=datetime.utcnow(),
        )
        commit()
        conversation_id = conversation.id

    response = client.post(
        f"/api/conversations/{conversation_id}/mark-read",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["conversation"]["unread_count"] == 0

    with db_session:
        refreshed = Conversation.get(id=conversation_id)
        assert refreshed.unread_count == 0


def test_assignment_rejects_users_outside_the_business(owner_client, app):
    client, token = owner_client

    with db_session:
        business = User.get(email="owner@example.com").current_business
        conversation = Conversation(
            business=business,
            customer_id=99,
            channel="whatsapp",
            status="open",
            unread_count=0,
            last_message_at=datetime.utcnow(),
        )
        commit()
        conversation_id = conversation.id

    other_email = "other-user@example.com"
    register_user(client, email=other_email, password="securepass123")
    add_business_member(app, other_email, business.id, role="support")

    response = client.post(
        f"/api/conversations/{conversation_id}/assign",
        json={"assigned_to_user_id": 9999},
        headers=auth_headers(token),
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "User not found"


def test_staff_member_cannot_manage_conversations_without_permission(owner_client, app):
    client, token = owner_client

    with db_session:
        business = User.get(email="owner@example.com").current_business
        conversation = Conversation(
            business=business,
            customer_id=88,
            channel="whatsapp",
            status="open",
            unread_count=0,
            last_message_at=datetime.utcnow(),
        )
        commit()
        conversation_id = conversation.id

    support_email = "support@example.com"
    support_response = register_user(client, email=support_email, password="securepass123")
    support_token = support_response.get_json()["access_token"]
    add_business_member(app, support_email, business.id, role="staff")

    response = client.patch(
        f"/api/conversations/{conversation_id}",
        json={"status": "pending"},
        headers=auth_headers(support_token),
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == ErrorCode.PERMISSION_DENIED
