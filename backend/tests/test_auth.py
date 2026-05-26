import pytest

from app.auth.services import create_password_reset_token
from app.users.models import User
from pony.orm import commit, db_session


def register_user(client, **overrides):
    payload = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "password": "securepass123",
    }
    payload.update(overrides)
    return client.post("/api/auth/register", json=payload)


@pytest.fixture
def registered_user(client):
    response = register_user(client)
    assert response.status_code == 201
    data = response.get_json()
    return data["user"], data["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestRegister:
    def test_register_success(self, client):
        response = register_user(client, email="new@example.com")
        assert response.status_code == 201
        data = response.get_json()
        assert data["user"]["email"] == "new@example.com"
        assert data["user"]["name"] == "Jane Doe"
        assert data["user"]["role"] is None
        assert data["user"]["is_active"] is True
        assert "password" not in data["user"]
        assert "password_hash" not in data["user"]
        assert data["access_token"]

    def test_register_duplicate_email(self, client, registered_user):
        response = register_user(client)
        assert response.status_code == 409
        assert response.get_json()["error"] == "Email already registered"

    def test_register_short_password(self, client):
        response = register_user(client, password="short", email="short@example.com")
        assert response.status_code == 400
        body = response.get_json()
        assert body["errors"]["password"] == "Password must be at least 8 characters long"

    def test_register_missing_name(self, client):
        response = register_user(client, name="", email="noname@example.com")
        assert response.status_code == 400
        assert response.get_json()["errors"]["name"] == "Name is required"

    def test_register_missing_email(self, client):
        response = register_user(client, email="")
        assert response.status_code == 400
        assert response.get_json()["errors"]["email"] == "Email is required"

    def test_register_missing_password(self, client):
        response = register_user(client, password="", email="nopass@example.com")
        assert response.status_code == 400
        assert response.get_json()["errors"]["password"] == "Password is required"

    def test_register_multiple_validation_errors(self, client):
        response = register_user(client, name="", email="", password="")
        assert response.status_code == 400
        errors = response.get_json()["errors"]
        assert errors["name"] == "Name is required"
        assert errors["email"] == "Email is required"
        assert errors["password"] == "Password is required"
        assert response.get_json()["error"] == "Please correct the errors below."


class TestLogin:
    def test_login_success(self, client, registered_user):
        response = client.post(
            "/api/auth/login",
            json={"email": "jane@example.com", "password": "securepass123"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["access_token"]
        assert data["user"]["email"] == "jane@example.com"

    def test_login_invalid_credentials(self, client, registered_user):
        response = client.post(
            "/api/auth/login",
            json={"email": "jane@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.get_json()["error"]

    def test_login_missing_email(self, client):
        response = client.post("/api/auth/login", json={"password": "securepass123"})
        assert response.status_code == 400
        assert response.get_json()["errors"]["email"] == "Email is required"

    def test_login_missing_password(self, client):
        response = client.post("/api/auth/login", json={"email": "jane@example.com"})
        assert response.status_code == 400
        assert response.get_json()["errors"]["password"] == "Password is required"

    def test_login_missing_email_and_password(self, client):
        response = client.post("/api/auth/login", json={})
        assert response.status_code == 400
        errors = response.get_json()["errors"]
        assert errors["email"] == "Email is required"
        assert errors["password"] == "Password is required"

    def test_login_accepts_username_alias(self, client, registered_user):
        response = client.post(
            "/api/auth/login",
            json={"username": "jane@example.com", "password": "securepass123"},
        )
        assert response.status_code == 200

    def test_login_inactive_user(self, client, app, registered_user):
        with app.app_context():

            @db_session
            def deactivate():
                user = User.get(email="jane@example.com")
                user.is_active = False
                commit()

            deactivate()

        response = client.post(
            "/api/auth/login",
            json={"email": "jane@example.com", "password": "securepass123"},
        )
        assert response.status_code == 403


class TestProtectedEndpoints:
    def test_me_requires_authentication(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_with_valid_token(self, client, registered_user):
        _, token = registered_user
        response = client.get("/api/auth/me", headers=auth_headers(token))
        assert response.status_code == 200
        assert response.get_json()["user"]["email"] == "jane@example.com"

    def test_me_rejects_invalid_token(self, client):
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_me_blocks_inactive_user(self, client, app, registered_user):
        user, token = registered_user
        with app.app_context():

            @db_session
            def deactivate():
                db_user = User.get(id=user["id"])
                db_user.is_active = False
                commit()

            deactivate()

        response = client.get("/api/auth/me", headers=auth_headers(token))
        assert response.status_code == 403


class TestLogout:
    def test_logout_revokes_token(self, client, registered_user):
        _, token = registered_user
        logout_response = client.post("/api/auth/logout", headers=auth_headers(token))
        assert logout_response.status_code == 200

        me_response = client.get("/api/auth/me", headers=auth_headers(token))
        assert me_response.status_code == 401
        body = me_response.get_json()
        assert body["error"] == "AUTH_REQUIRED"
        assert body["message"] == "Token revoked"


class TestPasswordReset:
    def test_forgot_password_generic_response(self, client, registered_user):
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "jane@example.com"},
        )
        assert response.status_code == 200
        assert "message" in response.get_json()

        unknown_response = client.post(
            "/api/auth/forgot-password",
            json={"email": "unknown@example.com"},
        )
        assert unknown_response.status_code == 200
        assert unknown_response.get_json()["message"] == response.get_json()["message"]

    def test_reset_password_success(self, client, app, registered_user):
        user, _ = registered_user
        with app.app_context():
            reset_token = create_password_reset_token(
                user["id"],
                app.config["PASSWORD_RESET_TOKEN_EXPIRES"],
            )

        response = client.post(
            "/api/auth/reset-password",
            json={"token": reset_token, "password": "newsecurepass123"},
        )
        assert response.status_code == 200

        login_response = client.post(
            "/api/auth/login",
            json={"email": "jane@example.com", "password": "newsecurepass123"},
        )
        assert login_response.status_code == 200

    def test_reset_password_rejects_invalid_token(self, client):
        response = client.post(
            "/api/auth/reset-password",
            json={"token": "invalid-token", "password": "newsecurepass123"},
        )
        assert response.status_code == 400

    def test_reset_password_requires_password(self, client):
        response = client.post(
            "/api/auth/reset-password",
            json={"token": "some-token", "password": ""},
        )
        assert response.status_code == 400
        assert response.get_json()["errors"]["password"] == "Password is required"

    def test_reset_token_is_single_use(self, client, app, registered_user):
        user, _ = registered_user
        with app.app_context():
            reset_token = create_password_reset_token(
                user["id"],
                app.config["PASSWORD_RESET_TOKEN_EXPIRES"],
            )

        first_response = client.post(
            "/api/auth/reset-password",
            json={"token": reset_token, "password": "anotherpass123"},
        )
        assert first_response.status_code == 200

        second_response = client.post(
            "/api/auth/reset-password",
            json={"token": reset_token, "password": "yetanother123"},
        )
        assert second_response.status_code == 400
