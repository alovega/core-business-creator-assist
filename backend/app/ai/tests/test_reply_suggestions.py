import json

from pony.orm import commit, db_session

from app.ai.providers import (
    AIProviderError,
    AIProviderResult,
)
from app.ai.services import (
    AIReplyService,
    SAFE_PRICING_FALLBACK,
)
from app.automations.models import FAQEntry
from app.businesses.models import Business
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.messages.models import Message
from app.testing.helpers import auth_headers


class FakeProvider:
    def __init__(self, text: str):
        self.text = text
        self.instructions = None
        self.input_text = None

    def generate(self, *, instructions: str, input_text: str) -> AIProviderResult:
        self.instructions = instructions
        self.input_text = input_text

        return AIProviderResult(text=self.text, request_id="req-test-123")


class FailingProvider:
    def generate(self, *, instructions: str, input_text: str) -> AIProviderResult:
        raise AIProviderError("provider unavailable")


def _business_id(client, token: str) -> int:
    response = client.get("/api/businesses/current", headers=auth_headers(token))

    assert response.status_code == 200

    return response.get_json()["business"]["id"]


def _create_conversation_with_context(business_id: int) -> int:
    with db_session:
        business = Business.get(id=business_id)

        customer = Customer(
            business=business,
            name="Alice",
            phone_number="15551234567",
        )

        commit()

        conversation = Conversation(
            business=business,
            customer_id=customer.id,
            channel="whatsapp",
            contact_phone_number="15551234567",
        )

        Message(
            business=business,
            conversation=conversation,
            customer_id=customer.id,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body=("Do you deliver and how much is it?"),
            status="received",
        )

        FAQEntry(
            business=business,
            question="Do you deliver?",
            answer=("Yes. Delivery is available " "within Nairobi."),
            keywords_json=[
                "deliver",
                "delivery",
            ],
        )

        commit()

        return conversation.id


def test_ai_reply_returns_suggestion_without_sending(owner_client, monkeypatch):
    client, token = owner_client

    business_id = _business_id(client, token)

    conversation_id = _create_conversation_with_context(business_id)

    provider = FakeProvider(
        "Yes, we deliver within Nairobi. " "How can I help further?"
    )

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        provider,
    )

    with db_session:
        before_count = Message.select().count()

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["suggestion"] == (
        "Yes, we deliver within Nairobi. How can I help further?"
    )

    assert payload["auto_sent"] is False
    assert payload["editable"] is True

    with db_session:
        assert Message.select().count() == before_count


def test_ai_reply_context_contains_business_customer_faqs_and_messages(
    owner_client, monkeypatch
):
    client, token = owner_client

    business_id = _business_id(
        client,
        token,
    )

    with db_session:
        business = Business.get(id=business_id)

        business.settings_json = {
            "description": ("A neighbourhood bakery"),
            "currency": "KES",
            "api_keys": {"secret": "must-not-leak"},
        }

        commit()

    conversation_id = _create_conversation_with_context(business_id)

    provider = FakeProvider("Yes, delivery is available " "within Nairobi.")

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        provider,
    )

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert provider.input_text is not None

    raw_context = provider.input_text.split(
        "CONTEXT_JSON:\n",
        1,
    )[1]

    context = json.loads(raw_context)

    assert context["business"]["name"] == "Acme Corp"

    assert context["business"]["settings"]["description"] == "A neighbourhood bakery"

    assert "api_keys" not in context["business"]["settings"]

    assert context["customer"] == {"name": "Alice"}

    assert context["active_faqs"][0]["question"] == "Do you deliver?"

    assert context["recent_messages"][0]["speaker"] == "customer"

    assert "how much" in context["recent_messages"][0]["text"].lower()


def test_inactive_faq_is_not_sent_to_ai(
    owner_client,
    monkeypatch,
):
    client, token = owner_client

    business_id = _business_id(
        client,
        token,
    )

    conversation_id = _create_conversation_with_context(business_id)

    with db_session:
        business = Business.get(id=business_id)

        FAQEntry(
            business=business,
            question="Old pricing",
            answer=("The old price was KES 1."),
            keywords_json=["price"],
            is_active=False,
        )

        commit()

    provider = FakeProvider("Yes, delivery is available " "within Nairobi.")

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        provider,
    )

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert provider.input_text is not None

    assert "Old pricing" not in provider.input_text

    assert "KES 1" not in provider.input_text


def test_unverified_price_is_blocked(
    owner_client,
    monkeypatch,
):
    client, token = owner_client

    business_id = _business_id(
        client,
        token,
    )

    conversation_id = _create_conversation_with_context(business_id)

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        FakeProvider("Delivery costs KES 9,999."),
    )

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    assert response.get_json()["suggestion"] == SAFE_PRICING_FALLBACK


def test_unverified_plain_price_is_blocked(
    owner_client,
    monkeypatch,
):
    client, token = owner_client

    business_id = _business_id(
        client,
        token,
    )

    conversation_id = _create_conversation_with_context(business_id)

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        FakeProvider("Delivery costs 9999."),
    )

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    assert response.get_json()["suggestion"] == SAFE_PRICING_FALLBACK


def test_verified_faq_price_is_allowed(
    owner_client,
    monkeypatch,
):
    client, token = owner_client

    business_id = _business_id(
        client,
        token,
    )

    conversation_id = _create_conversation_with_context(business_id)

    with db_session:
        business = Business.get(id=business_id)

        FAQEntry(
            business=business,
            question=("What is the delivery fee?"),
            answer=("The delivery fee is " "KES 250."),
            keywords_json=["delivery fee"],
        )

        commit()

    suggestion = "The delivery fee is KES 250."

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        FakeProvider(suggestion),
    )

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    assert response.get_json()["suggestion"] == suggestion


def test_verified_structured_business_price_is_allowed(
    owner_client,
    monkeypatch,
):
    client, token = owner_client

    business_id = _business_id(
        client,
        token,
    )

    conversation_id = _create_conversation_with_context(business_id)

    with db_session:
        business = Business.get(id=business_id)

        business.settings_json = {
            "currency": "KES",
            "pricing": {
                "delivery": {
                    "price": 300,
                }
            },
        }

        commit()

    suggestion = "Delivery costs KES 300."

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        FakeProvider(suggestion),
    )

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    assert response.get_json()["suggestion"] == suggestion


def test_provider_failure_is_handled_gracefully(
    owner_client,
    monkeypatch,
):
    client, token = owner_client

    business_id = _business_id(
        client,
        token,
    )

    conversation_id = _create_conversation_with_context(business_id)

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        FailingProvider(),
    )

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 503

    assert response.get_json() == {
        "error": (
            "AI reply suggestion is "
            "temporarily unavailable. "
            "Please write the reply manually."
        )
    }


def test_conversation_from_another_business_is_not_accessible(
    owner_client,
    monkeypatch,
):
    client, token = owner_client

    current_business_id = _business_id(
        client,
        token,
    )

    with db_session:
        other_business = Business(
            name="Other Business",
            slug="other-business",
            industry="retail",
        )

        other_conversation = Conversation(
            business=other_business,
            customer_id=999,
            channel="whatsapp",
            contact_phone_number=("15550000000"),
        )

        Message(
            business=other_business,
            conversation=other_conversation,
            customer_id=999,
            direction="incoming",
            channel="whatsapp",
            message_type="text",
            body="Hello",
            status="received",
        )

        commit()

        other_conversation_id = other_conversation.id

        other_business_id = other_business.id

    assert current_business_id != other_business_id

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        FakeProvider("Hello!"),
    )

    response = client.post(
        (f"/api/conversations/" f"{other_conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 404

    assert response.get_json()["error"] == "Conversation not found"


def test_empty_conversation_returns_422(
    owner_client,
    monkeypatch,
):
    client, token = owner_client

    business_id = _business_id(
        client,
        token,
    )

    with db_session:
        business = Business.get(id=business_id)

        conversation = Conversation(
            business=business,
            customer_id=123,
            channel="whatsapp",
            contact_phone_number=("15551234567"),
        )

        commit()

        conversation_id = conversation.id

    monkeypatch.setattr(
        AIReplyService,
        "_provider",
        FakeProvider("Hello"),
    )

    response = client.post(
        (f"/api/conversations/" f"{conversation_id}/" f"ai/suggest-reply"),
        headers=auth_headers(token),
    )

    assert response.status_code == 422

    assert response.get_json()["error"] == (
        "Conversation has no messages " "to reply to"
    )
