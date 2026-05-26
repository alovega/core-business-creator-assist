import pytest

from app.migrations.create_db import drop_postgres_database


def test_drop_postgres_database_noop_for_sqlite():
    drop_postgres_database("sqlite:///:memory:")


def test_drop_postgres_database_refuses_non_test_name():
    with pytest.raises(ValueError, match="_test"):
        drop_postgres_database(
            "postgresql://postgres:postgres@localhost:5432/business_creator"
        )
