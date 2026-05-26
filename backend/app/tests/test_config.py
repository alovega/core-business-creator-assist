import logging

import pytest

from app import create_app
from app.config import (
    ConfigurationError,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    _SETTING_ENV_MAP,
)


def test_development_uses_env_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    DevelopmentConfig.refresh_from_env()
    assert "business_creator" in DevelopmentConfig.SQLALCHEMY_DATABASE_URI


def test_testing_uses_separate_database_config(monkeypatch):
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/custom_test_db",
    )
    monkeypatch.setenv("TEST_REDIS_URL", "redis://localhost:6379/9")
    TestingConfig.refresh_from_env()
    assert TestingConfig.SQLALCHEMY_DATABASE_URI.endswith("custom_test_db")
    assert TestingConfig.REDIS_URL == "redis://localhost:6379/9"


def test_production_fails_when_required_config_missing(monkeypatch, caplog):
    monkeypatch.setenv("FLASK_ENV", "production")
    for setting in ProductionConfig.required_settings():
        monkeypatch.delenv(_SETTING_ENV_MAP.get(setting, setting), raising=False)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ConfigurationError, match="Missing required configuration"):
            create_app("production")

    assert any("Application startup aborted" in record.message for record in caplog.records)


def test_unknown_flask_env_fails_clearly(monkeypatch, caplog):
    monkeypatch.setenv("FLASK_ENV", "invalid-env")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ConfigurationError, match="Unknown FLASK_ENV"):
            create_app()

    assert any("Application startup aborted" in record.message for record in caplog.records)
