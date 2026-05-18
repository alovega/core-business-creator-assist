def test_health_returns_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "healthy"
    assert payload["checks"]["database"]["status"] == "up"
    assert payload["checks"]["redis"]["status"] == "up"
