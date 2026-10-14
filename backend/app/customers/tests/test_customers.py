from pony.orm import db_session

from app.businesses.models import Business
from app.customers.models import Customer
from app.customers.services import get_or_create_customer_from_whatsapp
from app.testing.helpers import add_business_member, auth_headers, create_business, register_user


def _owner_workspace(client, email="owner@example.com", business_name="Acme Corp"):
    registration = register_user(client, email=email)
    token = registration.get_json()["access_token"]
    created = create_business(client, token, name=business_name)
    assert created.status_code == 201
    data = created.get_json()
    return data["business"], data["access_token"]


def test_create_customer_normalizes_phone_and_serializes(client):
    business, token = _owner_workspace(client)

    response = client.post(
        "/api/customers",
        headers=auth_headers(token),
        json={
            "name": "Kelvin",
            "phone_number": "0712 345 678",
            "email": "KELVIN@example.com",
            "tags": ["VIP", "vip", " retail "],
            "notes": "Prefers WhatsApp",
        },
    )

    assert response.status_code == 201
    customer = response.get_json()["customer"]
    assert customer["business_id"] == business["id"]
    assert customer["normalized_phone_number"] == "254712345678"
    assert customer["email"] == "kelvin@example.com"
    assert customer["tags"] == ["VIP", "retail"]
    assert customer["source"] == "manual"
    assert customer["created_by_user_id"] is not None


def test_duplicate_customer_is_rejected_within_same_business(client):
    _, token = _owner_workspace(client)

    first = client.post(
        "/api/customers",
        headers=auth_headers(token),
        json={"phone_number": "+254712345678", "name": "First"},
    )
    second = client.post(
        "/api/customers",
        headers=auth_headers(token),
        json={"phone_number": "0712345678", "name": "Duplicate"},
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_same_phone_number_is_allowed_in_different_businesses(client):
    _, token_one = _owner_workspace(client, "one@example.com", "One Ltd")
    _, token_two = _owner_workspace(client, "two@example.com", "Two Ltd")

    one = client.post(
        "/api/customers",
        headers=auth_headers(token_one),
        json={"phone_number": "+254700000001"},
    )
    two = client.post(
        "/api/customers",
        headers=auth_headers(token_two),
        json={"phone_number": "+254700000001"},
    )

    assert one.status_code == 201
    assert two.status_code == 201
    assert one.get_json()["customer"]["business_id"] != two.get_json()["customer"]["business_id"]


def test_customer_from_another_business_is_not_accessible(client):
    _, token_one = _owner_workspace(client, "one@example.com", "One Ltd")
    _, token_two = _owner_workspace(client, "two@example.com", "Two Ltd")

    created = client.post(
        "/api/customers",
        headers=auth_headers(token_one),
        json={"phone_number": "+254711111111"},
    )
    customer_id = created.get_json()["customer"]["id"]

    response = client.get(
        f"/api/customers/{customer_id}",
        headers=auth_headers(token_two),
    )
    assert response.status_code == 404


def test_list_search_update_and_delete_customer(client):
    _, token = _owner_workspace(client)
    created = client.post(
        "/api/customers",
        headers=auth_headers(token),
        json={
            "name": "Alice Example",
            "phone_number": "+254722222222",
            "email": "alice@example.com",
            "tags": ["priority"],
            "source": "manual",
        },
    )
    customer_id = created.get_json()["customer"]["id"]

    listing = client.get(
        "/api/customers?q=alice&tag=priority&status=active",
        headers=auth_headers(token),
    )
    assert listing.status_code == 200
    assert listing.get_json()["pagination"]["total"] == 1

    search = client.get(
        "/api/customers/search?q=alice@example.com",
        headers=auth_headers(token),
    )
    assert search.status_code == 200
    assert len(search.get_json()["customers"]) == 1

    updated = client.patch(
        f"/api/customers/{customer_id}",
        headers=auth_headers(token),
        json={"name": "Alice Updated", "status": "inactive", "tags": ["returning"]},
    )
    assert updated.status_code == 200
    assert updated.get_json()["customer"]["name"] == "Alice Updated"
    assert updated.get_json()["customer"]["status"] == "inactive"

    deleted = client.delete(
        f"/api/customers/{customer_id}",
        headers=auth_headers(token),
    )
    assert deleted.status_code == 204


def test_whatsapp_customer_creation_is_idempotent(app):
    with app.app_context():
        @db_session
        def run():
            business = Business(name="WA Business", slug="wa-business", status="active")
            first, first_created = get_or_create_customer_from_whatsapp(
                business=business,
                phone_number="+254733333333",
                name="WhatsApp Contact",
            )
            second, second_created = get_or_create_customer_from_whatsapp(
                business=business,
                phone_number="254733333333",
                name="Changed Name",
            )
            assert first_created is True
            assert second_created is False
            assert first.id == second.id
            assert Customer.select(lambda c: c.business == business).count() == 1
            assert first.source == "whatsapp"

        run()


def test_staff_can_manage_but_cannot_delete_customers(client, app):
    business, owner_token = _owner_workspace(client)
    created = client.post(
        "/api/customers",
        headers=auth_headers(owner_token),
        json={"phone_number": "+254744444444"},
    )
    customer_id = created.get_json()["customer"]["id"]

    staff_registration = register_user(client, email="staff@example.com")
    staff_token = staff_registration.get_json()["access_token"]
    add_business_member(app, "staff@example.com", business["id"], role="staff")

    listing = client.get("/api/customers", headers=auth_headers(staff_token))
    assert listing.status_code == 200

    updated = client.patch(
        f"/api/customers/{customer_id}",
        headers=auth_headers(staff_token),
        json={"notes": "Handled by staff"},
    )
    assert updated.status_code == 200

    deleted = client.delete(
        f"/api/customers/{customer_id}",
        headers=auth_headers(staff_token),
    )
    assert deleted.status_code == 403