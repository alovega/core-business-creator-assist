from datetime import datetime

from pony.orm import commit, db_session

from app.automations.models import AutoResponseRule, FAQEntry
from app.automations.services import match_faq, match_rule, resolve_auto_response
from app.businesses.models import Business
from app.conversations.models import Conversation
from app.messages.models import Message
from app.testing.helpers import auth_headers


def _business_id(client, token: str) -> int:
    return client.get(
        "/api/businesses/current",
        headers=auth_headers(token),
    ).get_json()["business"]["id"]


def test_faq_crud_and_enable_disable(owner_client):
    client, token = owner_client

    response = client.post(
        "/api/automations/faqs",
        json={
            "question": "What are your opening hours?",
            "answer": "We are open from 8am to 5pm.",
            "keywords": ["opening hours", "hours", "OPENING HOURS"],
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201
    faq = response.get_json()["faq"]
    assert faq["keywords"] == ["opening hours", "hours"]
    assert faq["is_active"] is True

    response = client.patch(
        f"/api/automations/faqs/{faq['id']}",
        json={"is_active": False},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    assert response.get_json()["faq"]["is_active"] is False

    response = client.get(
        "/api/automations/faqs?active=false",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.get_json()["faqs"]] == [faq["id"]]

    response = client.delete(
        f"/api/automations/faqs/{faq['id']}",
        headers=auth_headers(token),
    )
    assert response.status_code == 204


def test_rule_crud_and_enable_disable(owner_client):
    client, token = owner_client

    response = client.post(
        "/api/automations/rules",
        json={
            "name": "Pricing question",
            "trigger_type": "keyword",
            "trigger_config": {
                "keywords": ["price", "pricing"],
                "cooldown_seconds": 120,
            },
            "response_text": "Our team can help you with pricing.",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201
    rule = response.get_json()["rule"]
    assert rule["trigger_type"] == "keyword"
    assert rule["trigger_config"]["cooldown_seconds"] == 120

    response = client.patch(
        f"/api/automations/rules/{rule['id']}",
        json={"is_active": False},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    assert response.get_json()["rule"]["is_active"] is False


def test_keyword_matching_prefers_specific_keyword(owner_client):
    client, token = owner_client
    business_id = _business_id(client, token)

    with db_session:
        business = Business.get(id=business_id)
        general = FAQEntry(
            business=business,
            question="Price?",
            answer="General pricing answer",
            keywords_json=["price"],
        )
        specific = FAQEntry(
            business=business,
            question="Enterprise price?",
            answer="Enterprise pricing answer",
            keywords_json=["enterprise price"],
        )
        AutoResponseRule(
            business=business,
            name="Human agent",
            trigger_type="keyword",
            trigger_config_json={"keywords": ["human agent"]},
            response_text="I will connect you to a human agent.",
        )
        commit()

        assert match_faq(business, "What is the enterprise price?").id == specific.id
        assert match_faq(business, "What is the price?").id == general.id
        assert match_faq(business, "This is a surprise") is None
        assert match_rule(business, "Can I speak to a HUMAN AGENT please?") is not None


def test_disabled_entries_do_not_match(owner_client):
    client, token = owner_client
    business_id = _business_id(client, token)

    with db_session:
        business = Business.get(id=business_id)
        FAQEntry(
            business=business,
            question="Delivery?",
            answer="Delivery answer",
            keywords_json=["delivery"],
            is_active=False,
        )
        AutoResponseRule(
            business=business,
            name="Disabled delivery rule",
            trigger_type="keyword",
            trigger_config_json={"keywords": ["delivery"]},
            response_text="Disabled response",
            is_active=False,
        )
        commit()

        assert match_faq(business, "Do you offer delivery?") is None
        assert match_rule(business, "Do you offer delivery?") is None


def test_duplicate_auto_response_is_suppressed(owner_client):
    client, token = owner_client
    business_id = _business_id(client, token)

    with db_session:
        business = Business.get(id=business_id)
        conversation = Conversation(
            business=business,
            customer_id=99,
            channel="whatsapp",
            contact_phone_number="15551234567",
        )
        rule = AutoResponseRule(
            business=business,
            name="Hours",
            trigger_type="keyword",
            trigger_config_json={
                "keywords": ["hours"],
                "cooldown_seconds": 120,
            },
            response_text="We are open from 8am to 5pm.",
        )
        commit()

        first_match = resolve_auto_response(
            business,
            "What are your hours?",
            conversation=conversation,
        )
        assert first_match is not None
        assert first_match.source_id == rule.id

        Message(
            business=business,
            conversation=conversation,
            customer_id=conversation.customer_id,
            direction="outgoing",
            channel="whatsapp",
            message_type="text",
            body=first_match.response_text,
            status="sent",
            created_at=datetime.utcnow(),
        )
        commit()

        duplicate = resolve_auto_response(
            business,
            "hours please",
            conversation=conversation,
        )
        assert duplicate is None
