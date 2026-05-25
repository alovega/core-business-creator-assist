import pytest

from app import create_app
from app.extensions import db
from app.users.models import User


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
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


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_token(client):
    response = register_user(client)
    assert response.status_code == 201
    return response.get_json()["access_token"]


def create_business(client, token, **overrides):
    payload = {"name": "Acme Corp"}
    payload.update(overrides)
    return client.post(
        "/api/businesses",
        json=payload,
        headers=auth_headers(token),
    )


class TestCreateBusiness:
    def test_create_business_success(self, client, auth_token):
        response = create_business(
            client,
            auth_token,
            phone_number="+1234567890",
            email="contact@acme.com",
            industry="retail",
        )
        assert response.status_code == 201
        business = response.get_json()["business"]
        assert business["name"] == "Acme Corp"
        assert business["slug"] == "acme-corp"
        assert business["phone_number"] == "+1234567890"
        assert business["email"] == "contact@acme.com"
        assert business["industry"] == "retail"
        assert business["plan"] == "free"
        assert business["status"] == "active"
        assert business["settings"] == {}

        me_response = client.get("/api/auth/me", headers=auth_headers(auth_token))
        assert me_response.get_json()["user"]["business_id"] == business["id"]

    def test_create_business_requires_auth(self, client):
        response = client.post("/api/businesses", json={"name": "Acme Corp"})
        assert response.status_code == 401

    def test_create_business_requires_name(self, client, auth_token):
        response = create_business(client, auth_token, name="")
        assert response.status_code == 400

    def test_create_business_only_once(self, client, auth_token):
        first = create_business(client, auth_token)
        assert first.status_code == 201
        second = create_business(client, auth_token, name="Other Corp")
        assert second.status_code == 409
        assert second.get_json()["error"] == "User already belongs to a business"

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
        assert response.get_json()["error"] == "No business workspace"

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


class TestTenantIsolation:
    def test_users_only_see_own_business(self, client, auth_token):
        create_business(client, auth_token, name="Tenant A")

        other_register = register_user(
            client, email="tenantb@example.com", name="Tenant B User"
        )
        other_token = other_register.get_json()["access_token"]
        create_business(client, other_token, name="Tenant B")

        response_a = client.get(
            "/api/businesses/current",
            headers=auth_headers(auth_token),
        )
        response_b = client.get(
            "/api/businesses/current",
            headers=auth_headers(other_token),
        )

        assert response_a.get_json()["business"]["name"] == "Tenant A"
        assert response_b.get_json()["business"]["name"] == "Tenant B"
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
            user = User.query.filter_by(email="orphan@example.com").one()
            assert user.business_id is None
