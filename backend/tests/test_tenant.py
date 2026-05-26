from app.auth.services import decode_access_token
from app.common.tenant import (
    BUSINESS_ID_HEADER,
    ensure_default_current_business,
    resolve_current_business,
)
from pony.orm import commit, db_session


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


def create_business(client, token, **overrides):
    payload = {
        "name": "Acme Corp",
        "phone_number": "+1234567890",
        "industry": "retail",
    }
    payload.update(overrides)
    return client.post(
        "/api/businesses",
        json=payload,
        headers=auth_headers(token),
    )


class TestLoginWorkspaceContext:
    def test_login_returns_accessible_businesses(self, client):
        register = register_user(client, email="multi@example.com")
        token = register.get_json()["access_token"]
        create_business(client, token, name="Workspace A")
        create_business(client, token, name="Workspace B")

        login = client.post(
            "/api/auth/login",
            json={"email": "multi@example.com", "password": "securepass123"},
        )
        assert login.status_code == 200
        body = login.get_json()
        assert len(body["businesses"]) == 2
        assert body["user"]["current_business_id"] is not None

    def test_login_sets_default_when_single_membership(self, client):
        register = register_user(client, email="solo@example.com")
        token = register.get_json()["access_token"]
        created = create_business(client, token)
        business_id = created.get_json()["business"]["id"]

        login = client.post(
            "/api/auth/login",
            json={"email": "solo@example.com", "password": "securepass123"},
        )
        body = login.get_json()
        assert body["user"]["current_business_id"] == business_id
        assert body["user"]["role"] == "owner"

        payload = decode_access_token(
            body["access_token"],
            client.application.config["JWT_SECRET"],
        )
        assert payload["business_id"] == business_id


class TestTenantResolution:
    def test_header_selects_workspace(self, client, app):
        register = register_user(client, email="header@example.com")
        token = register.get_json()["access_token"]
        first = create_business(client, token, name="First")
        second = create_business(client, token, name="Second")
        first_id = first.get_json()["business"]["id"]
        second_id = second.get_json()["business"]["id"]

        response = client.get(
            "/api/businesses/current",
            headers={
                **auth_headers(token),
                BUSINESS_ID_HEADER: str(first_id),
            },
        )
        assert response.status_code == 200
        assert response.get_json()["business"]["id"] == first_id

        response_b = client.get(
            "/api/businesses/current",
            headers={
                **auth_headers(token),
                BUSINESS_ID_HEADER: str(second_id),
            },
        )
        assert response_b.get_json()["business"]["id"] == second_id

    def test_switch_returns_token_with_business_claim(self, client):
        register = register_user(client, email="switch@example.com")
        token = register.get_json()["access_token"]
        first = create_business(client, token, name="One")
        second = create_business(client, token, name="Two")
        second_id = second.get_json()["business"]["id"]

        switched = client.post(
            "/api/businesses/switch",
            json={"business_id": second_id},
            headers=auth_headers(token),
        )
        assert switched.status_code == 200
        new_token = switched.get_json()["access_token"]
        payload = decode_access_token(
            new_token,
            client.application.config["JWT_SECRET"],
        )
        assert payload["business_id"] == second_id

        current = client.get(
            "/api/businesses/current",
            headers=auth_headers(new_token),
        )
        assert current.get_json()["business"]["id"] == second_id
        assert first.get_json()["business"]["id"] != second_id

    def test_resolve_current_business_helper(self, client, app):
        register = register_user(client, email="resolve@example.com")
        token = register.get_json()["access_token"]
        create_business(client, token)

        with app.app_context():

            @db_session
            def run():
                from app.users.models import User

                user = User.get(email="resolve@example.com")
                ensure_default_current_business(user)
                business, membership = resolve_current_business(user)
                assert business is not None
                assert membership is not None
                assert membership.role.key == "owner"

            run()
