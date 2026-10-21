"""API response standardization regression tests."""

from app.common.responses import (
    auth_error, not_found_error, server_error, success_response,
    validation_error,
)


def test_response_helpers(app):
    with app.app_context():
        resp, status = success_response({"id": 1}, "Created", 201)
        assert status == 201
        assert resp.get_json()["data"] == {"id": 1}
        assert resp.get_json()["success"] is True
        resp, status = validation_error({"email": "Required"})
        assert status == 400
        assert resp.get_json()["details"] == {"email": "Required"}
        assert resp.get_json()["code"] == "VALIDATION_ERROR"
        assert auth_error()[1] == 401
        assert not_found_error()[1] == 404
        assert server_error()[1] == 500


def test_existing_success_remains_compatible(client):
    response = client.get("/api/auth/me")
    body = response.get_json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["code"] == "AUTH_REQUIRED"
    assert isinstance(body["message"], str)


def test_legacy_validation_preserves_field_errors(client):
    response = client.post("/api/auth/register", json={})
    body = response.get_json()
    assert response.status_code == 400
    assert body["success"] is False
    assert body["details"] == body["errors"]
    assert body["code"] == "VALIDATION_ERROR"


def test_unknown_api_route_has_safe_json_error(client):
    response = client.get("/api/does-not-exist")
    body = response.get_json()
    assert response.status_code == 404
    assert body["success"] is False
    assert body["code"] == "NOT_FOUND"
    assert "traceback" not in str(body).lower()


def test_exception_is_logged_without_exposing_details(client, app, caplog):
    @app.get("/api/_raise-for-test")
    def fail():
        raise RuntimeError("secret internal details")

    with caplog.at_level("ERROR"):
        response = client.get("/api/_raise-for-test")
    body = response.get_json()
    assert response.status_code == 500
    assert body["success"] is False
    assert body["message"] == "Internal server error"
    assert "secret internal details" not in str(body)
    assert any("unhandled_exception" in record.getMessage() for record in caplog.records)