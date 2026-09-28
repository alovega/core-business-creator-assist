from decimal import Decimal

from pony.orm import commit, db_session

from app.businesses.models import Business
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.messages.models import Message
from app.payments.models import Payment
from app.testing.helpers import add_business_member, auth_headers, register_user


def create_customer_and_conversation(business_id: int) -> tuple[int, int]:
    with db_session:
        business = Business.get(id=business_id)
        customer = Customer(
            business=business,
            name="John Customer",
            phone_number="254700000001",
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


def test_payment_create_update_and_mark_paid(owner_client):
    client, token = owner_client
    headers = auth_headers(token)
    business_id = client.get("/api/businesses/current", headers=headers).get_json()[
        "business"
    ]["id"]
    customer_id, conversation_id = create_customer_and_conversation(business_id)

    response = client.post(
        "/api/payments",
        json={
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "amount": "2500.00",
            "currency": "KES",
            "reference": "INV-1001",
            "method": "mpesa",
            "notes": "Deposit",
        },
        headers=headers,
    )
    assert response.status_code == 201
    payment = response.get_json()["payment"]
    assert payment["business_id"] == business_id
    assert payment["amount"] == "2500.00"
    assert payment["status"] == "pending"
    assert payment["confirmed_by_user_id"] is None

    payment_id = payment["id"]
    update = client.patch(
        f"/api/payments/{payment_id}",
        json={"reference": "QWE123ABC", "notes": "Receipt supplied"},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.get_json()["payment"]["reference"] == "QWE123ABC"

    mark_paid = client.post(
        f"/api/payments/{payment_id}/mark-paid",
        headers=headers,
    )
    assert mark_paid.status_code == 200
    paid = mark_paid.get_json()["payment"]
    assert paid["status"] == "paid"
    assert paid["confirmed_by_user_id"] is not None
    assert paid["confirmed_at"] is not None


def test_payment_list_is_business_scoped(owner_client):
    client, token = owner_client
    headers = auth_headers(token)
    business_id = client.get("/api/businesses/current", headers=headers).get_json()[
        "business"
    ]["id"]
    customer_id, _ = create_customer_and_conversation(business_id)

    with db_session:
        own_business = Business.get(id=business_id)
        other_business = Business(
            name="Other Business",
            slug="other-business",
        )
        own_payment = Payment(
            business=own_business,
            customer_id=customer_id,
            amount=Decimal("100.00"),
            currency="KES",
            method="cash",
        )
        other_payment = Payment(
            business=other_business,
            customer_id=9999,
            amount=Decimal("200.00"),
            currency="KES",
            method="cash",
        )
        commit()
        own_payment_id = own_payment.id
        other_payment_id = other_payment.id

    response = client.get("/api/payments", headers=headers)
    assert response.status_code == 200
    ids = [item["id"] for item in response.get_json()["payments"]]
    assert own_payment_id in ids
    assert other_payment_id not in ids

    hidden = client.patch(
        f"/api/payments/{other_payment_id}",
        json={"notes": "should not work"},
        headers=headers,
    )
    assert hidden.status_code == 404


def test_staff_can_manage_payments(app, owner_client):
    client, owner_token = owner_client
    owner_headers = auth_headers(owner_token)
    business_id = client.get(
        "/api/businesses/current", headers=owner_headers
    ).get_json()["business"]["id"]
    customer_id, conversation_id = create_customer_and_conversation(business_id)

    staff_response = register_user(
        client,
        name="Staff User",
        email="staff@example.com",
        password="securepass123",
    )
    staff_token = staff_response.get_json()["access_token"]
    add_business_member(app, "staff@example.com", business_id, role="staff")

    response = client.post(
        "/api/payments",
        json={
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "amount": "500.00",
            "currency": "KES",
            "method": "cash",
        },
        headers=auth_headers(staff_token),
    )
    assert response.status_code == 201

    payment_id = response.get_json()["payment"]["id"]
    mark_paid = client.post(
        f"/api/payments/{payment_id}/mark-paid",
        headers=auth_headers(staff_token),
    )
    assert mark_paid.status_code == 200


def test_send_payment_reminder_uses_whatsapp(owner_client, monkeypatch):
    client, token = owner_client
    headers = auth_headers(token)
    business_id = client.get("/api/businesses/current", headers=headers).get_json()[
        "business"
    ]["id"]
    customer_id, conversation_id = create_customer_and_conversation(business_id)

    create = client.post(
        "/api/payments",
        json={
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "amount": "1200.00",
            "currency": "KES",
            "reference": "INV-2002",
            "method": "mpesa",
        },
        headers=headers,
    )
    payment_id = create.get_json()["payment"]["id"]

    monkeypatch.setattr(
        "app.payments.routes.send_whatsapp_message",
        lambda message, recipient: "wamid.payment-reminder",
    )

    response = client.post(
        f"/api/payments/{payment_id}/send-reminder",
        headers=headers,
    )
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["message"]["status"] == "sent"
    assert "KES 1200.00" in payload["message"]["body"]
    assert "INV-2002" in payload["message"]["body"]

    with db_session:
        message = Message.get(provider_message_id="wamid.payment-reminder")
        assert message is not None
        assert message.conversation.id == conversation_id
        assert message.customer_id == customer_id