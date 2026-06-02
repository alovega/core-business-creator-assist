from pony.orm import db_session

from app.testing.helpers import add_business_member, auth_headers, create_business, register_user
from app.users.models import User


def _create_customer(client, token, **overrides):
    payload = {
        "name": "John Customer",
        "phone_number": "+1 (202) 555-0100",
        "email": "john@example.com",
        "source": "manual",
        "tags": ["vip", "renewal"],
        "notes": "Important account",
        "status": "active",
    }
    payload.update(overrides)
    return client.post("/api/customers", json=payload, headers=auth_headers(token))


class TestCustomerCrud:
    def test_create_customer_success(self, client, owner_client):
        _, token = owner_client
        response = _create_customer(client, token)
        assert response.status_code == 201
        customer = response.get_json()["customer"]
        assert customer["name"] == "John Customer"
        assert customer["normalized_phone_number"] == "+12025550100"
        assert customer["source"] == "manual"
        assert "vip" in customer["tags"]

    def test_duplicate_customer_prevented_within_business(self, client, owner_client):
        _, token = owner_client
        first = _create_customer(client, token)
        assert first.status_code == 201

        second = _create_customer(client, token, phone_number="+12025550100")
        assert second.status_code == 409

    def test_same_phone_allowed_across_businesses(self, client, owner_client):
        _, owner_token = owner_client
        first = _create_customer(client, owner_token)
        assert first.status_code == 201

        second_user = register_user(client, email="owner2@example.com")
        second_token = second_user.get_json()["access_token"]
        create_business(client, second_token)
        second = _create_customer(client, second_token, email="owner2-customer@example.com")
        assert second.status_code == 201

    def test_get_update_delete_customer(self, client, owner_client):
        _, token = owner_client
        created = _create_customer(client, token)
        customer_id = created.get_json()["customer"]["id"]

        fetched = client.get(f"/api/customers/{customer_id}", headers=auth_headers(token))
        assert fetched.status_code == 200

        updated = client.patch(
            f"/api/customers/{customer_id}",
            json={"name": "Updated Name", "tags": ["new"], "notes": "Updated note"},
            headers=auth_headers(token),
        )
        assert updated.status_code == 200
        assert updated.get_json()["customer"]["name"] == "Updated Name"
        assert updated.get_json()["customer"]["tags"] == ["new"]

        deleted = client.delete(f"/api/customers/{customer_id}", headers=auth_headers(token))
        assert deleted.status_code == 200

        not_found = client.get(f"/api/customers/{customer_id}", headers=auth_headers(token))
        assert not_found.status_code == 404


class TestCustomerSearch:
    def test_search_by_name_phone_email_tag_source_status(self, client, owner_client):
        _, token = owner_client
        _create_customer(
            client,
            token,
            name="Alice Jones",
            phone_number="+1 415 555 0101",
            email="alice@example.com",
            tags=["vip", "priority"],
            source="manual",
            status="active",
        )
        _create_customer(
            client,
            token,
            name="Bob Smith",
            phone_number="+1 415 555 0102",
            email="bob@example.com",
            tags=["new"],
            source="api",
            status="archived",
        )

        by_name = client.get("/api/customers/search?q=alice", headers=auth_headers(token))
        assert by_name.status_code == 200
        assert len(by_name.get_json()["customers"]) == 1

        by_phone = client.get(
            "/api/customers/search?q=%2B14155550101",
            headers=auth_headers(token),
        )
        assert by_phone.status_code == 200
        assert len(by_phone.get_json()["customers"]) == 1

        by_email = client.get("/api/customers/search?q=bob@example.com", headers=auth_headers(token))
        assert len(by_email.get_json()["customers"]) == 1

        by_tag = client.get("/api/customers/search?tag=vip", headers=auth_headers(token))
        assert len(by_tag.get_json()["customers"]) == 1

        by_source = client.get("/api/customers/search?source=api", headers=auth_headers(token))
        assert len(by_source.get_json()["customers"]) == 1

        by_status = client.get(
            "/api/customers/search?status=archived",
            headers=auth_headers(token),
        )
        assert len(by_status.get_json()["customers"]) == 1


class TestWhatsAppCustomerResolution:
    def test_whatsapp_find_or_create_is_idempotent(self, client, owner_client):
        _, token = owner_client

        first = client.post(
            "/api/customers/resolve/whatsapp",
            json={"phone_number": "+44 20 7946 0018", "profile_name": "WA Contact"},
            headers=auth_headers(token),
        )
        assert first.status_code == 200
        first_payload = first.get_json()
        assert first_payload["created"] is True
        first_id = first_payload["customer"]["id"]

        second = client.post(
            "/api/customers/resolve/whatsapp",
            json={"phone_number": "+442079460018", "profile_name": "WA Contact"},
            headers=auth_headers(token),
        )
        assert second.status_code == 200
        second_payload = second.get_json()
        assert second_payload["created"] is False
        assert second_payload["customer"]["id"] == first_id


class TestRbacAndTenantIsolation:
    def test_support_can_view_but_cannot_manage_or_delete(self, client, app, owner_client):
        _, owner_token = owner_client
        created = _create_customer(client, owner_token)
        customer_id = created.get_json()["customer"]["id"]

        register_user(client, email="support-customers@example.com")
        with app.app_context():

            @db_session
            def _business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = _business_id()

        add_business_member(app, "support-customers@example.com", business_id, role="support")
        support_login = client.post(
            "/api/auth/login",
            json={"email": "support-customers@example.com", "password": "securepass123"},
        )
        support_token = support_login.get_json()["access_token"]

        can_view = client.get("/api/customers", headers=auth_headers(support_token))
        assert can_view.status_code == 200

        cannot_create = _create_customer(
            client,
            support_token,
            phone_number="+33123456789",
            email="support-customer@example.com",
        )
        assert cannot_create.status_code == 403

        cannot_delete = client.delete(
            f"/api/customers/{customer_id}",
            headers=auth_headers(support_token),
        )
        assert cannot_delete.status_code == 403

    def test_user_cannot_access_customer_from_another_business(self, client, owner_client):
        _, first_owner_token = owner_client
        created = _create_customer(client, first_owner_token)
        customer_id = created.get_json()["customer"]["id"]

        outsider = register_user(client, email="outsider-customers@example.com")
        outsider_token = outsider.get_json()["access_token"]
        create_business(client, outsider_token)

        forbidden = client.get(
            f"/api/customers/{customer_id}",
            headers=auth_headers(outsider_token),
        )
        assert forbidden.status_code == 404
