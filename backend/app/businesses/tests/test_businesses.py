from pony.orm import db_session

from app.testing.helpers import create_business
from app.testing.helpers import auth_headers, register_user
from app.users.models import User


class TestCreateBusiness:
    def test_create_business_success(self, client, auth_token):
        response = create_business(
            client,
            auth_token,
            phone_number="+1234567890",
            industry="retail",
        )
        assert response.status_code == 201
        business = response.get_json()["business"]
        assert business["name"] == "Acme Corp"
        assert business["slug"] == "acme-corp"
        assert business["phone_number"] == "+1234567890"
        assert business["email"] == "jane@example.com"
        assert business["industry"] == "retail"
        assert business["plan"] == "free"
        assert business["status"] == "active"
        assert business["settings"] == {}

        me_response = client.get("/api/auth/me", headers=auth_headers(auth_token))
        me_user = me_response.get_json()["user"]
        assert me_user["business_id"] == business["id"]
        assert me_user["role"] == "owner"

    def test_create_business_requires_auth(self, client):
        response = client.post(
            "/api/businesses",
            json={
                "name": "Acme Corp",
                "phone_number": "+1234567890",
                "industry": "retail",
            },
        )
        assert response.status_code == 401

    def test_create_business_sets_email_from_account(self, client, auth_token):
        response = create_business(client, auth_token)
        assert response.status_code == 201
        assert response.get_json()["business"]["email"] == "jane@example.com"

    def test_create_business_rejects_mismatched_email(self, client, auth_token):
        response = create_business(client, auth_token, email="other@example.com")
        assert response.status_code == 400
        assert (
            response.get_json()["errors"]["email"]
            == "Business email must match your account email"
        )

    def test_create_business_requires_name(self, client, auth_token):
        response = create_business(client, auth_token, name="")
        assert response.status_code == 400
        assert response.get_json()["errors"]["name"] == "Business name is required"

    def test_create_business_missing_required_fields(self, client, auth_token):
        response = client.post(
            "/api/businesses",
            json={},
            headers=auth_headers(auth_token),
        )
        assert response.status_code == 400
        errors = response.get_json()["errors"]
        assert errors["name"] == "Business name is required"
        assert errors["phone_number"] == "Phone number is required"
        assert errors["industry"] == "Industry is required"
        assert "email" not in errors

    def test_create_business_missing_phone_number(self, client, auth_token):
        response = create_business(client, auth_token, phone_number="")
        assert response.status_code == 400
        assert response.get_json()["errors"]["phone_number"] == "Phone number is required"

    def test_create_business_missing_industry(self, client, auth_token):
        response = create_business(client, auth_token, industry="")
        assert response.status_code == 400
        assert response.get_json()["errors"]["industry"] == "Industry is required"

    def test_create_business_invalid_plan(self, client, auth_token):
        response = create_business(client, auth_token, plan="invalid-plan")
        assert response.status_code == 400
        assert "Plan must be one of:" in response.get_json()["errors"]["plan"]

    def test_create_business_invalid_field_types(self, client, auth_token):
        response = client.post(
            "/api/businesses",
            json={
                "name": "Acme Corp",
                "email": 12345,
                "phone_number": True,
                "industry": ["retail"],
                "plan": 99,
            },
            headers=auth_headers(auth_token),
        )
        assert response.status_code == 400
        errors = response.get_json()["errors"]
        assert errors["email"] == "Email must be a string"
        assert errors["phone_number"] == "Phone number must be a string"
        assert errors["industry"] == "Industry must be a string"
        assert errors["plan"] == "Plan must be a string"
        assert response.get_json()["error"] == "Please correct the errors below."

    def test_user_can_create_multiple_businesses(self, client, auth_token):
        first = create_business(client, auth_token)
        assert first.status_code == 201
        second = create_business(client, auth_token, name="Other Corp")
        assert second.status_code == 201
        assert second.get_json()["business"]["name"] == "Other Corp"
        assert second.get_json()["membership"]["role"] == "owner"

        list_response = client.get(
            "/api/businesses",
            headers=auth_headers(auth_token),
        )
        assert list_response.status_code == 200
        assert len(list_response.get_json()["businesses"]) == 2

    def test_unique_slug_for_duplicate_names(self, client, auth_token):
        create_business(client, auth_token, name="Acme Corp")

        other_register = register_user(
            client, email="other@example.com", name="Other User"
        )
        other_token = other_register.get_json()["access_token"]
        second = create_business(client, other_token, name="Acme Corp")
        assert second.status_code == 201
        assert second.get_json()["business"]["slug"] == "acme-corp-2"


class TestCurrentBusiness:
    def test_get_current_business(self, client, auth_token):
        create_response = create_business(client, auth_token)
        business_id = create_response.get_json()["business"]["id"]

        response = client.get(
            "/api/businesses/current",
            headers=auth_headers(auth_token),
        )
        assert response.status_code == 200
        assert response.get_json()["business"]["id"] == business_id

    def test_get_current_without_business(self, client, auth_token):
        response = client.get(
            "/api/businesses/current",
            headers=auth_headers(auth_token),
        )
        assert response.status_code == 404
        body = response.get_json()
        assert body["error"] == "BUSINESS_REQUIRED"
        assert "No business workspace" in body["message"]

    def test_update_current_business(self, client, auth_token):
        create_business(client, auth_token)
        response = client.patch(
            "/api/businesses/current",
            json={
                "name": "Acme International",
                "industry": "services",
                "plan": "starter",
            },
            headers=auth_headers(auth_token),
        )
        assert response.status_code == 200
        business = response.get_json()["business"]
        assert business["name"] == "Acme International"
        assert business["industry"] == "services"
        assert business["plan"] == "starter"


class TestBusinessSettings:
    def test_get_and_update_settings(self, client, auth_token):
        create_business(client, auth_token)

        get_response = client.get(
            "/api/businesses/current/settings",
            headers=auth_headers(auth_token),
        )
        assert get_response.status_code == 200
        assert get_response.get_json()["settings"] == {}

        patch_response = client.patch(
            "/api/businesses/current/settings",
            json={"settings": {"timezone": "Africa/Lagos", "locale": "en"}},
            headers=auth_headers(auth_token),
        )
        assert patch_response.status_code == 200
        assert patch_response.get_json()["settings"]["timezone"] == "Africa/Lagos"
        assert patch_response.get_json()["settings"]["locale"] == "en"

        merge_response = client.patch(
            "/api/businesses/current/settings",
            json={"settings": {"notifications": True}},
            headers=auth_headers(auth_token),
        )
        assert merge_response.status_code == 200
        settings = merge_response.get_json()["settings"]
        assert settings["timezone"] == "Africa/Lagos"
        assert settings["notifications"] is True

    def test_update_settings_requires_object(self, client, auth_token):
        create_business(client, auth_token)
        response = client.patch(
            "/api/businesses/current/settings",
            json={"settings": "invalid"},
            headers=auth_headers(auth_token),
        )
        assert response.status_code == 400


class TestBusinessSwitching:
    def test_switch_between_member_businesses(self, client, auth_token):
        first = create_business(client, auth_token, name="Workspace A")
        second = create_business(client, auth_token, name="Workspace B")
        business_a_id = first.get_json()["business"]["id"]
        business_b_id = second.get_json()["business"]["id"]

        switch_a = client.post(
            "/api/businesses/switch",
            json={"business_id": business_a_id},
            headers=auth_headers(auth_token),
        )
        assert switch_a.status_code == 200
        current = client.get(
            "/api/businesses/current",
            headers=auth_headers(auth_token),
        )
        assert current.get_json()["business"]["id"] == business_a_id

        switch_b = client.post(
            "/api/businesses/switch",
            json={"business_id": business_b_id},
            headers=auth_headers(auth_token),
        )
        assert switch_b.status_code == 200
        current = client.get(
            "/api/businesses/current",
            headers=auth_headers(auth_token),
        )
        assert current.get_json()["business"]["id"] == business_b_id

    def test_cannot_switch_to_non_member_business(self, client, auth_token):
        create_business(client, auth_token)
        other_register = register_user(client, email="outsider2@example.com")
        other_token = other_register.get_json()["access_token"]
        other_business = create_business(client, other_token)
        other_id = other_business.get_json()["business"]["id"]

        response = client.post(
            "/api/businesses/switch",
            json={"business_id": other_id},
            headers=auth_headers(auth_token),
        )
        assert response.status_code == 403


class TestBusinessMembers:
    def test_owner_can_invite_and_list_members(self, client, auth_token):
        create_business(client, auth_token)
        invitee = register_user(client, email="member@example.com")

        invite = client.post(
            "/api/businesses/current/members/invite",
            json={"email": "member@example.com", "role": "staff"},
            headers=auth_headers(auth_token),
        )
        assert invite.status_code == 201
        assert invite.get_json()["membership"]["status"] == "invited"
        assert invite.get_json()["membership"]["role"] == "staff"

        members = client.get(
            "/api/businesses/current/members",
            headers=auth_headers(auth_token),
        )
        assert members.status_code == 200
        emails = {m["user"]["email"] for m in members.get_json()["members"]}
        assert "jane@example.com" in emails
        assert "member@example.com" in emails
        assert invitee.status_code == 201

    def test_duplicate_membership_rejected(self, client, auth_token):
        create_business(client, auth_token)
        register_user(client, email="dup@example.com")
        client.post(
            "/api/businesses/current/members/invite",
            json={"email": "dup@example.com", "role": "staff"},
            headers=auth_headers(auth_token),
        )
        second = client.post(
            "/api/businesses/current/members/invite",
            json={"email": "dup@example.com", "role": "admin"},
            headers=auth_headers(auth_token),
        )
        assert second.status_code == 409


class TestTenantIsolation:
    def test_users_only_see_current_workspace(self, client, auth_token):
        create_business(client, auth_token, name="Tenant A")
        create_business(client, auth_token, name="Tenant B")

        other_register = register_user(
            client, email="tenantb@example.com", name="Tenant B User"
        )
        other_token = other_register.get_json()["access_token"]
        create_business(client, other_token, name="Other Tenant")

        response_a = client.get(
            "/api/businesses/current",
            headers=auth_headers(auth_token),
        )
        response_b = client.get(
            "/api/businesses/current",
            headers=auth_headers(other_token),
        )

        assert response_a.get_json()["business"]["name"] == "Tenant B"
        assert response_b.get_json()["business"]["name"] == "Other Tenant"
        assert (
            response_a.get_json()["business"]["id"]
            != response_b.get_json()["business"]["id"]
        )

    def test_register_ignores_client_business_id(self, client, app):
        response = register_user(
            client,
            email="orphan@example.com",
            business_id=999,
        )
        assert response.status_code == 201
        assert response.get_json()["user"]["business_id"] is None

        with app.app_context():

            @db_session
            def check_user():
                user = User.get(email="orphan@example.com")
                assert user.business_id is None

            check_user()
