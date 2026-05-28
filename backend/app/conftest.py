"""
Shared pytest configuration for all colocated tests under ``app/``.

Module-specific tests (``app/auth/tests/``, ``app/businesses/tests/``, etc.)
inherit these fixtures automatically; add a local ``conftest.py`` only when a
module needs fixtures that do not belong in the shared suite.
"""

import pytest
from pony.orm import db_session

from app import create_app
from app.db import db
from app.testing.helpers import create_business, register_user


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    application = create_app("testing")
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_database():
    """Isolate tests on the shared in-memory Pony database."""
    from app.common.rbac.permissions import clear_permission_cache

    @db_session
    def _clean():
        if db.provider is None:
            return
        clear_permission_cache()
        for table in (
            "role_permissions",
            "business_memberships",
            "permissions",
            "roles",
            "users",
            "businesses",
            "database_version",
        ):
            try:
                db.execute(f'DELETE FROM "{table}"')
            except Exception:
                pass

    _clean()

    if db.provider is not None:
        from app.common.rbac.seed import ensure_rbac_seeded

        ensure_rbac_seeded()

    yield
    _clean()


@pytest.fixture
def auth_token(client):
    response = register_user(client)
    assert response.status_code == 201
    return response.get_json()["access_token"]


@pytest.fixture
def registered_user(client):
    response = register_user(client)
    assert response.status_code == 201
    data = response.get_json()
    return data["user"], data["access_token"]


@pytest.fixture
def owner_client(client):
    response = register_user(client, email="owner@example.com")
    token = response.get_json()["access_token"]
    create_business(client, token)
    return client, token
