from datetime import datetime
from decimal import Decimal

from pony.orm import commit, db_session

from app.bookings.models import Booking
from app.businesses.models import Business
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.leads.models import Lead
from app.messages.models import Message
from app.payments.models import Payment
from app.testing.helpers import auth_headers


def _seed_dashboard_data(business_id: int):
    with db_session:
        business = Business.get(id=business_id)
        customer = Customer(
            business=business,
            name="Dashboard Customer",
            phone_number="254700000001",
            normalized_phone_number="254700000001",
            status="active",
            created_at=datetime(2026, 9, 29, 8, 0),
        )
        commit()

        conversation = Conversation(
            business=business,
            customer_id=customer.id,
            channel="whatsapp",
            contact_phone_number="254700000001",
            unread_count=2,
            created_at=datetime(2026, 9, 30, 8, 0),
            updated_at=datetime(2026, 9, 30, 8, 10),
        )
        commit()

        Lead(
            business=business,
            conversation=conversation,
            customer_id=customer.id,
            stage="new",
            value=1500.0,
            created_at=datetime(2026, 9, 30, 8, 5),
        )
        Booking(
            business=business,
            customer_id=customer.id,
            conversation=conversation,
            service_name="Consultation",
            scheduled_at=datetime(2026, 9, 30, 12, 0),
            duration_minutes=60,
            status="confirmed",
            created_at=datetime(2026, 9, 29, 12, 0),
        )
        Payment(
            business=business,
            customer_id=customer.id,
            conversation=conversation,
            amount=Decimal("2500.00"),
            currency="KES",
            method="mpesa",
            status="pending",
            created_at=datetime(2026, 9, 30, 9, 0),
        )
        Message(
            business=business,
            conversation=conversation,
            customer_id=customer.id,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body="Hello",
            status="received",
            created_at=datetime(2026, 9, 30, 10, 0),
        )
        Message(
            business=business,
            conversation=conversation,
            customer_id=customer.id,
            direction="outgoing",
            channel="whatsapp",
            message_type="text",
            body="Hi there",
            status="sent",
            created_at=datetime(2026, 9, 30, 10, 2),
        )
        commit()


def test_summary_is_business_scoped_and_date_filtered(owner_client):
    client, token = owner_client
    headers = auth_headers(token)
    business_id = client.get("/api/businesses/current", headers=headers).get_json()[
        "business"
    ]["id"]
    _seed_dashboard_data(business_id)

    with db_session:
        other_business = Business(name="Other Dashboard Business", slug="other-dashboard")
        commit()
        other_customer = Customer(
            business=other_business,
            phone_number="254700000002",
            normalized_phone_number="254700000002",
            status="active",
        )
        commit()
        other_conversation = Conversation(
            business=other_business,
            customer_id=other_customer.id,
            channel="whatsapp",
            unread_count=8,
            updated_at=datetime(2026, 9, 30, 8, 0),
        )
        commit()
        Lead(
            business=other_business,
            conversation=other_conversation,
            stage="new",
            created_at=datetime(2026, 9, 30, 8, 0),
        )
        commit()

    response = client.get(
        "/api/dashboard/summary?start_date=2026-09-30&end_date=2026-09-30",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["business_id"] == business_id
    assert payload["metrics"] == {
        "active_customers": 1,
        "average_response_time_seconds": 120.0,
        "bookings": 1,
        "new_leads": 1,
        "pending_payments": 1,
        "unread_conversations": 1,
    }

    empty_range = client.get(
        "/api/dashboard/summary?start_date=2026-09-29&end_date=2026-09-29",
        headers=headers,
    )
    assert empty_range.status_code == 200
    empty_metrics = empty_range.get_json()["metrics"]
    assert empty_metrics["new_leads"] == 0
    assert empty_metrics["bookings"] == 0
    assert empty_metrics["pending_payments"] == 0
    assert empty_metrics["average_response_time_seconds"] is None
    # Snapshot cards intentionally remain current-state metrics.
    assert empty_metrics["active_customers"] == 1
    assert empty_metrics["unread_conversations"] == 1


def test_dashboard_detail_endpoints(owner_client):
    client, token = owner_client
    headers = auth_headers(token)
    business_id = client.get("/api/businesses/current", headers=headers).get_json()[
        "business"
    ]["id"]
    _seed_dashboard_data(business_id)
    query = "?start_date=2026-09-30&end_date=2026-09-30"

    conversations = client.get(f"/api/dashboard/conversations{query}", headers=headers)
    assert conversations.status_code == 200
    assert conversations.get_json()["metrics"]["unread_conversations"] == 1
    assert conversations.get_json()["metrics"]["average_response_time_seconds"] == 120.0

    leads = client.get(f"/api/dashboard/leads{query}", headers=headers)
    assert leads.status_code == 200
    assert leads.get_json()["metrics"]["by_stage"]["new"] == 1
    assert leads.get_json()["metrics"]["total_value"] == 1500.0

    bookings = client.get(f"/api/dashboard/bookings{query}", headers=headers)
    assert bookings.status_code == 200
    assert bookings.get_json()["metrics"]["by_status"]["confirmed"] == 1

    payments = client.get(f"/api/dashboard/payments{query}", headers=headers)
    assert payments.status_code == 200
    assert payments.get_json()["metrics"]["pending"] == 1
    assert payments.get_json()["metrics"]["totals_by_currency"]["KES"] == "2500.00"


def test_dashboard_rejects_invalid_date_range(owner_client):
    client, token = owner_client
    response = client.get(
        "/api/dashboard/summary?start_date=2026-10-01&end_date=2026-09-30",
        headers=auth_headers(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "start_date must be before end_date"