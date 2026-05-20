import pytest

from app import create_app
from app.auth.services import create_password_reset_token
from app.extensions import db
from app.users.models import User


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


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
        assert data["user"]["role"] == "user"
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
        assert response.get_json()["error"] == "Invalid credentials"

    def test_login_inactive_user(self, client, app, registered_user):
        with app.app_context():
            user = User.query.filter_by(email="jane@example.com").one()
            user.is_active = False
            db.session.commit()

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
            db_user = db.session.get(User, user["id"])
            db_user.is_active = False
            db.session.commit()

        response = client.get("/api/auth/me", headers=auth_headers(token))
        assert response.status_code == 403


class TestLogout:
    def test_logout_revokes_token(self, client, registered_user):
        _, token = registered_user
        logout_response = client.post("/api/auth/logout", headers=auth_headers(token))
        assert logout_response.status_code == 200

        me_response = client.get("/api/auth/me", headers=auth_headers(token))
        assert me_response.status_code == 401
        assert me_response.get_json()["error"] == "Token revoked"


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
