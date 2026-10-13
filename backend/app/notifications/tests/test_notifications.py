from datetime import datetime, timedelta
from decimal import Decimal

from pony.orm import commit, db_session, select

from app.automations.engine import dispatch_new_message_received
from app.automations.models import Automation
from app.businesses.models import Business
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.messages.models import Message
from app.notifications.models import Notification
from app.testing.helpers import add_business_member, auth_headers, register_user
from app.users.models import User


def _business_id(client, token: str) -> int:
    return client.get(
        "/api/businesses/current",
        headers=auth_headers(token),
    ).get_json()["business"]["id"]


def _create_customer_and_conversation(business_id: int) -> tuple[int, int]:
    with db_session:
        business = Business.get(id=business_id)
        customer = Customer(
            business=business,
            name="Notification Customer",
            phone_number="+254700000001",
            normalized_phone_number="254700000001",
            source="manual",
        )
        commit()
        conversation = Conversation(
            business=business,
            customer_id=customer.id,
            channel="whatsapp",
            contact_phone_number="254700000001",
        )
        commit()
        return customer.id, conversation.id


def test_notifications_are_scoped_to_current_business_and_user(app, owner_client):
    client, owner_token = owner_client
    business_id = _business_id(client, owner_token)

    staff_response = register_user(
        client,
        name="Staff User",
        email="notification-staff@example.com",
        password="securepass123",
    )
    staff_token = staff_response.get_json()["access_token"]
    add_business_member(app, "notification-staff@example.com", business_id, role="staff")

    with db_session:
        business = Business.get(id=business_id)
        owner = User.get(email="owner@example.com")
        staff = User.get(email="notification-staff@example.com")
        other_business = Business(name="Other Business", slug="notification-other")

        own = Notification(
            business=business,
            user=owner,
            title="Owner notification",
            message="Visible to owner",
            type="new_lead",
            link_url="/leads/1",
        )
        staff_only = Notification(
            business=business,
            user=staff,
            title="Staff notification",
            message="Visible to staff",
            type="new_message",
            link_url="/conversations/1",
        )
        other_business_notification = Notification(
            business=other_business,
            user=owner,
            title="Other business",
            message="Must not leak across tenants",
            type="booking_created",
            link_url="/bookings/1",
        )
        commit()
        own_id = own.id
        staff_only_id = staff_only.id
        other_business_id = other_business_notification.id

    owner_response = client.get(
        "/api/notifications",
        headers=auth_headers(owner_token),
    )
    assert owner_response.status_code == 200
    owner_ids = {item["id"] for item in owner_response.get_json()["notifications"]}
    assert own_id in owner_ids
    assert staff_only_id not in owner_ids
    assert other_business_id not in owner_ids
    assert owner_response.get_json()["unread_count"] == 1

    hidden = client.post(
        f"/api/notifications/{staff_only_id}/read",
        headers=auth_headers(owner_token),
    )
    assert hidden.status_code == 404

    marked = client.post(
        f"/api/notifications/{own_id}/read",
        headers=auth_headers(owner_token),
    )
    assert marked.status_code == 200
    assert marked.get_json()["notification"]["is_read"] is True

    unread = client.get(
        "/api/notifications?is_read=false",
        headers=auth_headers(owner_token),
    )
    assert unread.status_code == 200
    assert unread.get_json()["notifications"] == []
    assert unread.get_json()["unread_count"] == 0

    staff_response = client.get(
        "/api/notifications",
        headers=auth_headers(staff_token),
    )
    assert staff_response.status_code == 200
    assert [item["id"] for item in staff_response.get_json()["notifications"]] == [
        staff_only_id
    ]


def test_required_business_events_create_persistent_notifications(app, owner_client):
    client, owner_token = owner_client
    headers = auth_headers(owner_token)
    business_id = _business_id(client, owner_token)

    register_user(
        client,
        name="Staff User",
        email="event-staff@example.com",
        password="securepass123",
    )
    add_business_member(app, "event-staff@example.com", business_id, role="staff")
    customer_id, conversation_id = _create_customer_and_conversation(business_id)

    with db_session:
        business = Business.get(id=business_id)
        conversation = Conversation.get(id=conversation_id)
        incoming = Message(
            business=business,
            conversation=conversation,
            customer_id=customer_id,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body="Hello from WhatsApp",
            status="received",
        )
        commit()
        dispatch_new_message_received(incoming)

    lead_response = client.post(
        "/api/leads",
        json={"conversation_id": conversation_id, "stage": "new"},
        headers=headers,
    )
    assert lead_response.status_code == 201

    booking_response = client.post(
        "/api/bookings",
        json={
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "service_name": "Consultation",
            "scheduled_at": (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z",
            "duration_minutes": 60,
        },
        headers=headers,
    )
    assert booking_response.status_code == 201

    payment_response = client.post(
        "/api/payments",
        json={
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "amount": format(Decimal("2500.00"), "f"),
            "currency": "KES",
            "method": "mpesa",
        },
        headers=headers,
    )
    assert payment_response.status_code == 201

    with db_session:
        business = Business.get(id=business_id)
        conversation = Conversation.get(id=conversation_id)
        Automation(
            business=business,
            name="Broken automation",
            trigger_type="new_message_received",
            action_type="update_lead_stage",
            action_config_json={"stage": "paid"},
        )
        second_incoming = Message(
            business=business,
            conversation=conversation,
            customer_id=customer_id,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body="Trigger failure",
            status="received",
        )
        commit()
        runs = dispatch_new_message_received(second_incoming)
        assert len(runs) == 1
        assert runs[0].status == "failed"

        owner = User.get(email="owner@example.com")
        staff = User.get(email="event-staff@example.com")
        owner_types = {
            item.type
            for item in select(
                notification
                for notification in Notification
                if notification.business == business and notification.user == owner
            )
        }
        staff_types = {
            item.type
            for item in select(
                notification
                for notification in Notification
                if notification.business == business and notification.user == staff
            )
        }

    required_types = {
        "new_message",
        "new_lead",
        "booking_created",
        "payment_pending",
        "automation_failed",
    }
    assert required_types <= owner_types
    assert required_types <= staff_types