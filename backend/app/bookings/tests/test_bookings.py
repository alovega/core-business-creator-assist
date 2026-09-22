from pony.orm import commit, db_session

from app.automations.models import Automation
from app.businesses.models import Business
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.messages.models import Message
from app.testing.helpers import auth_headers


def create_customer_and_conversation(business_id: int) -> tuple[int, int]:
    with db_session:
        business = Business.get(id=business_id)
        customer = Customer(
            business=business,
            name="John Customer",
            phone_number="15551234567",
        )
        commit()
        conversation = Conversation(
            business=business,
            customer_id=customer.id,
            channel="whatsapp",
            contact_phone_number="15551234567",
        )
        commit()
        return customer.id, conversation.id


def test_booking_crud(owner_client):
    client, token = owner_client
    headers = auth_headers(token)
    business_id = client.get("/api/businesses/current", headers=headers).get_json()[
        "business"
    ]["id"]
    customer_id, conversation_id = create_customer_and_conversation(business_id)

    create_response = client.post(
        "/api/bookings",
        json={
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "service_name": "Consultation",
            "scheduled_at": "2026-09-25T10:30:00Z",
            "duration_minutes": 60,
            "notes": "First appointment",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    booking = create_response.get_json()["booking"]
    assert booking["business_id"] == business_id
    assert booking["customer_id"] == customer_id
    assert booking["conversation_id"] == conversation_id
    assert booking["status"] == "pending"

    booking_id = booking["id"]

    detail_response = client.get(f"/api/bookings/{booking_id}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.get_json()["booking"]["service_name"] == "Consultation"

    list_response = client.get(
        f"/api/bookings?status=pending&customer_id={customer_id}", headers=headers
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.get_json()["bookings"]] == [booking_id]

    update_response = client.patch(
        f"/api/bookings/{booking_id}",
        json={
            "status": "confirmed",
            "duration_minutes": 90,
            "notes": "Customer confirmed",
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    updated = update_response.get_json()["booking"]
    assert updated["status"] == "confirmed"
    assert updated["duration_minutes"] == 90
    assert updated["notes"] == "Customer confirmed"

    delete_response = client.delete(f"/api/bookings/{booking_id}", headers=headers)
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/bookings/{booking_id}", headers=headers)
    assert missing_response.status_code == 404


def test_booking_requires_customer_and_matching_conversation(owner_client):
    client, token = owner_client
    headers = auth_headers(token)
    business_id = client.get("/api/businesses/current", headers=headers).get_json()[
        "business"
    ]["id"]
    customer_id, conversation_id = create_customer_and_conversation(business_id)

    with db_session:
        other_customer = Customer(
            business=Business.get(id=business_id),
            name="Other Customer",
            phone_number="15550001111",
        )
        commit()
        other_customer_id = other_customer.id

    response = client.post(
        "/api/bookings",
        json={
            "customer_id": other_customer_id,
            "conversation_id": conversation_id,
            "service_name": "Consultation",
            "scheduled_at": "2026-09-25T10:30:00Z",
            "duration_minutes": 60,
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == (
        "conversation_id must belong to the selected customer"
    )

    unknown_customer = client.post(
        "/api/bookings",
        json={
            "customer_id": customer_id + 1000,
            "service_name": "Consultation",
            "scheduled_at": "2026-09-25T10:30:00Z",
            "duration_minutes": 60,
        },
        headers=headers,
    )
    assert unknown_customer.status_code == 404


def test_booking_created_event_can_send_confirmation(owner_client, monkeypatch):
    client, token = owner_client
    headers = auth_headers(token)
    business_id = client.get("/api/businesses/current", headers=headers).get_json()[
        "business"
    ]["id"]
    customer_id, conversation_id = create_customer_and_conversation(business_id)

    with db_session:
        Automation(
            business=Business.get(id=business_id),
            name="Booking confirmation",
            trigger_type="booking_created",
            trigger_config_json={},
            action_type="send_whatsapp_message",
            action_config_json={
                "message": "Your {service_name} booking is confirmed for {scheduled_at}."
            },
            is_active=True,
        )
        commit()

    monkeypatch.setattr(
        "app.automations.engine.send_whatsapp_message",
        lambda message, recipient: "wamid.booking-confirmation",
    )

    response = client.post(
        "/api/bookings",
        json={
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "service_name": "Consultation",
            "scheduled_at": "2026-09-25T10:30:00Z",
            "duration_minutes": 60,
        },
        headers=headers,
    )
    assert response.status_code == 201

    with db_session:
        message = Message.get(provider_message_id="wamid.booking-confirmation")
        assert message is not None
        assert message.status == "sent"
        assert "Consultation" in message.body
