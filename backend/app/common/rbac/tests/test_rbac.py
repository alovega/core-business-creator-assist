from pony.orm import db_session

from app.common.rbac.access import ErrorCode
from app.common.rbac.permissions import PermissionKey, membership_has_permission
from app.testing.helpers import add_business_member, auth_headers, create_business, register_user
from app.users.models import User


class TestRoleAssignment:
    def test_register_ignores_client_role(self, client, app):
        response = register_user(
            client,
            email="secure@example.com",
            role="owner",
        )
        assert response.status_code == 201
        assert response.get_json()["user"]["role"] is None

        with app.app_context():

            @db_session
            def check():
                user = User.get(email="secure@example.com")
                assert user.role is None

            check()

    def test_business_creator_becomes_owner(self, client, owner_client):
        _, token = owner_client
        me = client.get("/api/auth/me", headers=auth_headers(token))
        assert me.get_json()["user"]["role"] == "owner"


class TestOwnerOnlySettings:
    def test_staff_cannot_update_owner_only_settings(self, client, app, owner_client):
        _, owner_token = owner_client

        staff_register = register_user(client, email="staff@example.com")
        staff_token = staff_register.get_json()["access_token"]

        with app.app_context():

            @db_session
            def get_business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = get_business_id()
        add_business_member(app, "staff@example.com", business_id, role="staff")

        response = client.patch(
            "/api/businesses/current/settings",
            json={"settings": {"billing": {"plan": "pro"}}},
            headers=auth_headers(staff_token),
        )
        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == ErrorCode.PERMISSION_DENIED
        assert "owner-only settings" in body["message"]

    def test_staff_cannot_update_plan_on_business(self, client, app, owner_client):
        register_user(client, email="staff2@example.com")
        with app.app_context():

            @db_session
            def get_business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = get_business_id()
        add_business_member(app, "staff2@example.com", business_id, role="staff")
        staff_token = client.post(
            "/api/auth/login",
            json={"email": "staff2@example.com", "password": "securepass123"},
        ).get_json()["access_token"]

        response = client.patch(
            "/api/businesses/current",
            json={"plan": "enterprise"},
            headers=auth_headers(staff_token),
        )
        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == ErrorCode.PERMISSION_DENIED
        assert "owner-only fields" in body["message"]

    def test_owner_can_update_owner_only_settings(self, client, owner_client):
        _, token = owner_client
        response = client.patch(
            "/api/businesses/current/settings",
            json={"settings": {"billing": {"plan": "pro"}, "timezone": "UTC"}},
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        assert response.get_json()["settings"]["billing"]["plan"] == "pro"

    def test_staff_cannot_see_owner_only_settings(self, client, app, owner_client):
        _, owner_token = owner_client
        client.patch(
            "/api/businesses/current/settings",
            json={"settings": {"billing": {"plan": "pro"}, "locale": "en"}},
            headers=auth_headers(owner_token),
        )

        register_user(client, email="staff3@example.com")
        with app.app_context():

            @db_session
            def get_business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = get_business_id()
        add_business_member(app, "staff3@example.com", business_id, role="staff")
        staff_token = client.post(
            "/api/auth/login",
            json={"email": "staff3@example.com", "password": "securepass123"},
        ).get_json()["access_token"]

        response = client.get(
            "/api/businesses/current/settings",
            headers=auth_headers(staff_token),
        )
        assert response.status_code == 200
        settings = response.get_json()["settings"]
        assert "billing" not in settings
        assert settings["locale"] == "en"


class TestCrossBusinessAccess:
    def test_cannot_access_another_business_by_id(self, client, owner_client):
        _, owner_token = owner_client

        other_register = register_user(client, email="other@example.com")
        other_token = other_register.get_json()["access_token"]
        other_business = create_business(client, other_token)
        other_id = other_business.get_json()["business"]["id"]

        response = client.get(
            f"/api/businesses/{other_id}",
            headers=auth_headers(owner_token),
        )
        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == ErrorCode.MEMBERSHIP_REQUIRED
        assert "Access denied" in body["message"]


class TestUserPermissions:
    def test_staff_cannot_list_users(self, client, app, owner_client):
        register_user(client, email="staff4@example.com")
        with app.app_context():

            @db_session
            def get_business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = get_business_id()
        add_business_member(app, "staff4@example.com", business_id, role="staff")
        staff_token = client.post(
            "/api/auth/login",
            json={"email": "staff4@example.com", "password": "securepass123"},
        ).get_json()["access_token"]

        response = client.get("/api/users", headers=auth_headers(staff_token))
        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == ErrorCode.PERMISSION_DENIED
        assert PermissionKey.MANAGE_MEMBERS.value in body["message"]

    def test_owner_can_list_users(self, client, owner_client):
        _, token = owner_client
        response = client.get("/api/users", headers=auth_headers(token))
        assert response.status_code == 200
        emails = {u["email"] for u in response.get_json()["users"]}
        assert "owner@example.com" in emails

    def test_cannot_fetch_user_from_another_business(self, client, app, owner_client):
        _, owner_token = owner_client

        other_register = register_user(client, email="outsider@example.com")
        other_token = other_register.get_json()["access_token"]
        create_business(client, other_token)

        with app.app_context():

            @db_session
            def get_outsider_id():
                return User.get(email="outsider@example.com").id

            outsider_id = get_outsider_id()

        response = client.get(
            f"/api/users/{outsider_id}",
            headers=auth_headers(owner_token),
        )
        assert response.status_code == 404


class TestPermissionErrors:
    def test_permission_denied_message_is_clear(self, client, app, owner_client):
        register_user(client, email="support@example.com")
        with app.app_context():

            @db_session
            def get_business_id():
                return User.get(email="owner@example.com").current_business_id

            business_id = get_business_id()
        add_business_member(app, "support@example.com", business_id, role="support")
        support_token = client.post(
            "/api/auth/login",
            json={"email": "support@example.com", "password": "securepass123"},
        ).get_json()["access_token"]

        response = client.patch(
            "/api/businesses/current/settings",
            json={"settings": {"locale": "fr"}},
            headers=auth_headers(support_token),
        )
        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == ErrorCode.PERMISSION_DENIED
        assert PermissionKey.MANAGE_BUSINESS_SETTINGS.value in body["message"]

