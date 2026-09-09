from pony.orm import commit, db_session

from app.businesses.models import Business
from app.conversations.models import Conversation
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


def test_create_and_filter_leads_from_conversation(owner_client):
    client, token = owner_client
    business_id = client.get(
        "/api/businesses/current", headers=auth_headers(token)
    ).get_json()["business"]["id"]
    me = client.get("/api/auth/me", headers=auth_headers(token)).get_json()["user"]
    conversation_id = create_conversation(business_id)

    response = client.post(
        "/api/leads",
        json={
            "conversation_id": conversation_id,
            "value": 2500,
            "source": "website",
            "notes": "Interested in the monthly plan",
            "assigned_to_user_id": me["id"],
        },
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    lead = response.get_json()["lead"]
    assert lead["business_id"] == business_id
    assert lead["conversation_id"] == conversation_id
    assert lead["customer_id"] == 42
    assert lead["stage"] == "new"
    assert lead["assigned_to_user_id"] == me["id"]

    list_response = client.get(
        f"/api/leads?stage=new&assignee_id={me['id']}",
        headers=auth_headers(token),
    )
    assert list_response.status_code == 200
    items = list_response.get_json()["leads"]
    assert len(items) == 1
    assert items[0]["id"] == lead["id"]


def test_update_and_move_stage(owner_client):
    client, token = owner_client
    business_id = client.get(
        "/api/businesses/current", headers=auth_headers(token)
    ).get_json()["business"]["id"]
    me = client.get("/api/auth/me", headers=auth_headers(token)).get_json()["user"]
    conversation_id = create_conversation(business_id)

    response = client.post(
        "/api/leads",
        json={
            "conversation_id": conversation_id,
            "source": "facebook",
            "assigned_to_user_id": me["id"],
        },
        headers=auth_headers(token),
    )

    lead_id = response.get_json()["lead"]["id"]

    update_response = client.patch(
        f"/api/leads/{lead_id}",
        json={
            "stage": "interested",
            "notes": "Asked for a demo",
        },
        headers=auth_headers(token),
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["lead"]["stage"] == "interested"
    assert update_response.get_json()["lead"]["notes"] == "Asked for a demo"

    move_response = client.post(
        f"/api/leads/{lead_id}/move-stage",
        json={"stage": "booked"},
        headers=auth_headers(token),
    )
    assert move_response.status_code == 200
    assert move_response.get_json()["lead"]["stage"] == "booked"
