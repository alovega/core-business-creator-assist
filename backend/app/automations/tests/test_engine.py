from pony.orm import commit, db_session

from app.automations.engine import dispatch_new_message_received
from app.automations.models import Automation, AutomationRun
from app.businesses.models import Business
from app.conversations.models import Conversation
from app.messages.models import Message
from app.testing.helpers import auth_headers


def _business_id(client, token: str) -> int:
    return client.get(
        "/api/businesses/current",
        headers=auth_headers(token),
    ).get_json()["business"]["id"]


def test_create_automation_and_list_runs(owner_client):
    client, token = owner_client

    response = client.post(
        "/api/automations",
        json={
            "name": "Notify staff about inbound messages",
            "trigger_type": "new_message_received",
            "action_type": "notify_staff",
            "action_config": {"message": "New message: {body}"},
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201
    automation = response.get_json()["automation"]

    business_id = _business_id(client, token)
    with db_session:
        business = Business.get(id=business_id)
        conversation = Conversation(
            business=business,
            customer_id=42,
            channel="whatsapp",
            contact_phone_number="15551234567",
        )
        message = Message(
            business=business,
            conversation=conversation,
            customer_id=42,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body="Hello",
            status="received",
        )
        commit()

        runs = dispatch_new_message_received(message)
        assert len(runs) == 1
        assert runs[0].status == "success"
        assert runs[0].automation.id == automation["id"]

    response = client.get(
        "/api/automations/runs",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    run = response.get_json()["runs"][0]
    assert run["automation_id"] == automation["id"]
    assert run["trigger_type"] == "new_message_received"
    assert run["status"] == "success"


def test_failed_automation_is_logged_without_raising(owner_client):
    client, token = owner_client
    business_id = _business_id(client, token)

    with db_session:
        business = Business.get(id=business_id)
        automation = Automation(
            business=business,
            name="Broken lead update",
            trigger_type="new_message_received",
            action_type="update_lead_stage",
            action_config_json={"stage": "paid"},
        )
        conversation = Conversation(
            business=business,
            customer_id=99,
            channel="whatsapp",
        )
        message = Message(
            business=business,
            conversation=conversation,
            customer_id=99,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body="Hello",
            status="received",
        )
        commit()

        runs = dispatch_new_message_received(message)
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert "lead_id is required" in runs[0].error_message
        assert AutomationRun.get(automation=automation).status == "failed"


def test_automation_events_are_business_isolated(owner_client):
    client, token = owner_client
    business_id = _business_id(client, token)

    with db_session:
        business = Business.get(id=business_id)
        other_business = Business(name="Other", slug="other-business")
        Automation(
            business=other_business,
            name="Other business automation",
            trigger_type="new_message_received",
            action_type="notify_staff",
            action_config_json={"message": "Should never run"},
        )
        conversation = Conversation(
            business=business,
            customer_id=7,
            channel="whatsapp",
        )
        message = Message(
            business=business,
            conversation=conversation,
            customer_id=7,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body="Hello",
            status="received",
        )
        commit()

        assert dispatch_new_message_received(message) == []
        assert AutomationRun.select().count() == 0