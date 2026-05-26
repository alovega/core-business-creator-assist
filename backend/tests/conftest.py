import pytest

from app import create_app
from app.db import db


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
    from pony.orm import db_session

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
