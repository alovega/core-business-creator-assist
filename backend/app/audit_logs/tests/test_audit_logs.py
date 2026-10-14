"""Audit history contract: tenant filtering, safe metadata and action hooks."""
from pony.orm import db_session, select
from app.audit_logs.models import AuditLog
from app.audit_logs.services import record_audit_event
from app.testing.helpers import auth_headers, create_business, register_user


def test_record_audit_event_redacts_unknown_fields(app):
    with app.app_context(), db_session:
        assert not record_audit_event(business_id=None, user_id=1, action="login", resource_type="user")
        assert record_audit_event(business_id=81, user_id=7, action="message_sent",
                                  resource_type="message", resource_id=11,
                                  metadata={"channel": "whatsapp", "body": "secret", "password": "secret"})
        entry = select(x for x in AuditLog if x.business_id == 81).first()
        assert entry.metadata_json == {"channel": "whatsapp"}


def test_login_writes_workspace_scoped_event(client):
    registration = register_user(client)
    token = registration.get_json()["access_token"]
    business = create_business(client, token)
    assert business.status_code in (200, 201)
    response = client.post("/api/auth/login", json={"email": "jane@example.com", "password": "securepass123"})
    assert response.status_code == 200
    with db_session:
        logs = list(select(x for x in AuditLog if x.action == "login"))
        assert len(logs) == 1
        assert logs[0].business_id is not None
        assert logs[0].metadata_json == {}


def test_audit_logs_read_filtered_by_business(client):
    first = register_user(client, email="owner1@example.com")
    token1 = first.get_json()["access_token"]
    b1 = create_business(client, token1).get_json()["business"]["id"]
    second = register_user(client, email="owner2@example.com")
    token2 = second.get_json()["access_token"]
    b2 = create_business(client, token2, name="Other Business").get_json()["business"]["id"]
    with db_session:
        record_audit_event(business_id=b1, user_id=None, action="automation_changed", resource_type="automation", resource_id=1)
        record_audit_event(business_id=b2, user_id=None, action="automation_changed", resource_type="automation", resource_id=2)
    response = client.get("/api/audit-logs", headers=auth_headers(token1))
    assert response.status_code == 200
    entries = response.get_json()["audit_logs"]
    assert entries
    assert all(row["business_id"] == b1 for row in entries)
    assert all(row["resource_id"] != 2 for row in entries)
    assert client.get("/api/audit-logs?limit=101", headers=auth_headers(token1)).status_code == 400