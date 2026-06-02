from pony.orm import db_session

from app.testing.helpers import add_business_member, auth_headers, create_business, register_user
from app.users.models import User
from app.whatsapp.models import WhatsAppIntegration
from app.whatsapp.services import decrypt_secret


def _create_integration(client, token, **overrides):
    payload = {
        "phone_number_id": "123456789",
        "whatsapp_business_account_id": "waba-1",
        "display_phone_number": "+12025550000",
        "access_token": "meta-token",
        "verify_token": "verify-123",
        "app_secret": "meta-secret",
    }
    payload.update(overrides)
    return client.post(
        "/api/whatsapp/integration",
        json=payload,
        headers=auth_headers(token),
    )


class TestWhatsAppIntegration:
    def test_integration_setup_create_and_get(self, client, owner_client):
        _, token = owner_client
        created = _create_integration(client, token)
        assert created.status_code == 201
        get_response = client.get("/api/whatsapp/integration", headers=auth_headers(token))
        assert get_response.status_code == 200
        integration = get_response.get_json()["integration"]
        assert integration["phone_number_id"] == "123456789"
        assert integration["status"] == "connected"
        assert "access_token" not in integration
        assert "app_secret" not in integration
        assert "verify_token" not in integration
        assert "access_token_encrypted" not in integration

    def test_integration_secrets_are_encrypted_at_rest(self, client, app, owner_client):
        _, token = owner_client
        created = _create_integration(
            client,
            token,
            access_token="super-secret-access",
            app_secret="super-secret-app",
        )
        assert created.status_code == 201
        with app.app_context():
            with db_session:
                integration = WhatsAppIntegration.get(phone_number_id="123456789")
                assert integration is not None
                assert integration.access_token_encrypted != "super-secret-access"
                assert integration.app_secret != "super-secret-app"
                assert decrypt_secret(integration.access_token_encrypted) == "super-secret-access"
                assert decrypt_secret(integration.app_secret) == "super-secret-app"

    def test_patch_and_disconnect_integration(self, client, app, owner_client):
        _, owner_token = owner_client
        create = _create_integration(client, owner_token)
        assert create.status_code == 201
        patch = client.patch(
            "/api/whatsapp/integration",
            json={
                "phone_number_id": "123456789",
                "display_phone_number": "+12025559999",
            },
            headers=auth_headers(owner_token),
        )
        assert patch.status_code == 200
        assert patch.get_json()["integration"]["display_phone_number"] == "+12025559999"
        delete = client.delete(
            "/api/whatsapp/integration?phone_number_id=123456789",
            headers=auth_headers(owner_token),
        )
        assert delete.status_code == 200
        with app.app_context():
            with db_session:
                integration = WhatsAppIntegration.get(phone_number_id="123456789")
                assert integration is not None
                assert integration.status == "disconnected"
                assert integration.disconnected_at is not None


class TestWhatsAppOutboundAndAccessControl:
    def test_authorized_user_can_send_message(self, client, owner_client, monkeypatch):
        _, token = owner_client
        created = _create_integration(client, token)
        assert created.status_code == 201

        def _fake_send(*, integration, to, body):
            assert integration.phone_number_id == "123456789"
            assert to == "+12025550111"
            assert body == "hello from agent"
            return {
                "ok": True,
                "provider": "whatsapp",
                "provider_message_id": "wamid.outbound.1",
                "recipient_wa_id": "12025550111",
            }

        monkeypatch.setattr("app.whatsapp.routes._send_message_to_whatsapp", _fake_send)
        response = client.post(
            "/api/whatsapp/send-message",
            json={"phone_number": "+12025550111", "body": "hello from agent"},
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        payload = response.get_json()["result"]
        assert payload["provider_message_id"] == "wamid.outbound.1"

    def test_authorized_user_can_send_test_message(self, client, owner_client, monkeypatch):
        _, token = owner_client
        _create_integration(client, token)

        class _FakeClient:
            def __init__(self, *, phone_number_id, access_token, api_version):
                self.phone_number_id = phone_number_id
                self.access_token = access_token
                self.api_version = api_version

            def send_test_message(self, *, to, body):
                assert to == "+12025550112"
                assert body == "test body"
                return {
                    "ok": True,
                    "provider": "whatsapp",
                    "provider_message_id": "wamid.test.1",
                    "recipient_wa_id": "12025550112",
                }

        monkeypatch.setattr("app.whatsapp.routes.WhatsAppClient", _FakeClient)
        response = client.post(
            "/api/whatsapp/test-message",
            json={"phone_number": "+12025550112", "body": "test body"},
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        assert response.get_json()["result"]["provider_message_id"] == "wamid.test.1"

    def test_rbac_blocks_user_without_send_permission(self, client, app, owner_client):
        _, owner_token = owner_client
        _create_integration(client, owner_token)

        register_user(client, email="support-wa@example.com")
        with app.app_context():
            with db_session:
                business_id = User.get(email="owner@example.com").current_business_id
        add_business_member(app, "support-wa@example.com", business_id, role="support")
        login = client.post(
            "/api/auth/login",
            json={"email": "support-wa@example.com", "password": "securepass123"},
        )
        support_token = login.get_json()["access_token"]
        response = client.post(
            "/api/whatsapp/send-message",
            json={"phone_number": "+12025550113", "body": "blocked"},
            headers=auth_headers(support_token),
        )
        assert response.status_code == 403

    def test_tenant_isolation_for_other_business(self, client, owner_client):
        _, token = owner_client
        _create_integration(client, token)
        outsider = register_user(client, email="outsider-wa@example.com")
        outsider_token = outsider.get_json()["access_token"]
        create_business(client, outsider_token)
        response = client.post(
            "/api/whatsapp/send-message",
            json={"phone_number": "+12025550114", "body": "should fail"},
            headers=auth_headers(outsider_token),
        )
        assert response.status_code == 409

    def test_manage_whatsapp_permission_required_for_integration_endpoints(
        self, client, app, owner_client
    ):
        _, owner_token = owner_client
        _create_integration(client, owner_token)

        register_user(client, email="support-manage-wa@example.com")
        with app.app_context():
            with db_session:
                business_id = User.get(email="owner@example.com").current_business_id
        add_business_member(app, "support-manage-wa@example.com", business_id, role="support")
        login = client.post(
            "/api/auth/login",
            json={"email": "support-manage-wa@example.com", "password": "securepass123"},
        )
        support_token = login.get_json()["access_token"]

        get_response = client.get("/api/whatsapp/integration", headers=auth_headers(support_token))
        assert get_response.status_code == 403
        patch_response = client.patch(
            "/api/whatsapp/integration",
            json={"phone_number_id": "123456789", "display_phone_number": "+12025550001"},
            headers=auth_headers(support_token),
        )
        assert patch_response.status_code == 403

    def test_integration_response_never_exposes_secrets(self, client, owner_client):
        _, token = owner_client
        _create_integration(client, token, access_token="super-secret", app_secret="very-secret")
        response = client.get("/api/whatsapp/integration", headers=auth_headers(token))
        assert response.status_code == 200
        data = response.get_json()["integration"]
        assert "access_token" not in data
        assert "app_secret" not in data
        assert "access_token_encrypted" not in data
        assert "verify_token" not in data

        with db_session:
            integration = WhatsAppIntegration.get(
                business=User.get(email="owner@example.com").current_business
            )
            assert integration is not None
            assert integration.access_token_encrypted != "super-secret"
