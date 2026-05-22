import logging
import os
from typing import ClassVar

logger = logging.getLogger(__name__)

# Maps Flask config attribute names to environment variable names for error messages.
_SETTING_ENV_MAP: dict[str, str] = {
    "SQLALCHEMY_DATABASE_URI": "DATABASE_URL",
    "SECRET_KEY": "SECRET_KEY",
    "JWT_SECRET": "JWT_SECRET",
    "REDIS_URL": "REDIS_URL",
    "CELERY_BROKER_URL": "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND": "CELERY_RESULT_BACKEND",
    "WHATSAPP_PHONE_NUMBER_ID": "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_ACCESS_TOKEN": "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_VERIFY_TOKEN": "WHATSAPP_VERIFY_TOKEN",
    "META_APP_SECRET": "META_APP_SECRET",
    "AI_API_KEY": "AI_API_KEY",
    "STORAGE_BUCKET": "STORAGE_BUCKET",
    "STORAGE_REGION": "STORAGE_REGION",
    "AWS_ACCESS_KEY_ID": "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY": "AWS_SECRET_ACCESS_KEY",
    "FRONTEND_URL": "FRONTEND_URL",
}


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _env(key: str, default: str | None = None) -> str:
    return os.environ.get(key, default or "")


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes")


def log_configuration_error(error: ConfigurationError) -> None:
    """Emit a clear error log before the process exits on invalid configuration."""
    from app.common.logging import log_startup_error

    log_startup_error(f"Application startup aborted: {error}", exc=error)


class BaseConfig:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict] = {
        "pool_pre_ping": True,
    }

    SECRET_KEY = ""
    JWT_SECRET = ""
    JWT_ACCESS_TOKEN_EXPIRES = 3600
    PASSWORD_RESET_TOKEN_EXPIRES = 3600
    SQLALCHEMY_DATABASE_URI = ""

    REDIS_URL = "redis://localhost:6379/0"
    CELERY_BROKER_URL = ""
    CELERY_RESULT_BACKEND = ""

    WHATSAPP_PHONE_NUMBER_ID = ""
    WHATSAPP_ACCESS_TOKEN = ""
    WHATSAPP_VERIFY_TOKEN = ""
    WHATSAPP_API_VERSION = "v21.0"

    META_APP_SECRET = ""

    AI_API_KEY = ""
    AI_MODEL = "gpt-4o-mini"

    STORAGE_BACKEND = "local"
    STORAGE_BUCKET = ""
    STORAGE_REGION = ""
    AWS_ACCESS_KEY_ID = ""
    AWS_SECRET_ACCESS_KEY = ""
    STORAGE_LOCAL_PATH = "uploads"

    FRONTEND_URL = ""

    LOG_DIR = "logs"
    LOG_LEVEL = "INFO"
    LOG_JSON = True

    @classmethod
    def refresh_from_env(cls) -> None:
        redis_url = _env("REDIS_URL", "redis://localhost:6379/0")
        cls.SECRET_KEY = _env("SECRET_KEY")
        cls.JWT_SECRET = _env("JWT_SECRET")
        cls.JWT_ACCESS_TOKEN_EXPIRES = int(_env("JWT_ACCESS_TOKEN_EXPIRES", "3600"))
        cls.PASSWORD_RESET_TOKEN_EXPIRES = int(
            _env("PASSWORD_RESET_TOKEN_EXPIRES", "3600")
        )
        cls.SQLALCHEMY_DATABASE_URI = _env("DATABASE_URL")
        cls.REDIS_URL = redis_url
        cls.CELERY_BROKER_URL = _env("CELERY_BROKER_URL") or redis_url
        cls.CELERY_RESULT_BACKEND = _env("CELERY_RESULT_BACKEND") or redis_url

        cls.WHATSAPP_PHONE_NUMBER_ID = _env("WHATSAPP_PHONE_NUMBER_ID")
        cls.WHATSAPP_ACCESS_TOKEN = _env("WHATSAPP_ACCESS_TOKEN")
        cls.WHATSAPP_VERIFY_TOKEN = _env("WHATSAPP_VERIFY_TOKEN")
        cls.WHATSAPP_API_VERSION = _env("WHATSAPP_API_VERSION", "v21.0")

        cls.META_APP_SECRET = _env("META_APP_SECRET")

        cls.AI_API_KEY = _env("AI_API_KEY")
        cls.AI_MODEL = _env("AI_MODEL", "gpt-4o-mini")

        cls.STORAGE_BACKEND = _env("STORAGE_BACKEND", "local")
        cls.STORAGE_BUCKET = _env("STORAGE_BUCKET")
        cls.STORAGE_REGION = _env("STORAGE_REGION")
        cls.AWS_ACCESS_KEY_ID = _env("AWS_ACCESS_KEY_ID")
        cls.AWS_SECRET_ACCESS_KEY = _env("AWS_SECRET_ACCESS_KEY")
        cls.STORAGE_LOCAL_PATH = _env("STORAGE_LOCAL_PATH", "uploads")

        cls.FRONTEND_URL = _env("FRONTEND_URL")
        cls.LOG_DIR = _env("LOG_DIR", "logs")
        cls.LOG_LEVEL = _env("LOG_LEVEL", "INFO")
        cls.LOG_JSON = _env_bool("LOG_JSON", True)

    @classmethod
    def required_settings(cls) -> tuple[str, ...]:
        return ()

    @classmethod
    def _missing_settings(cls) -> list[str]:
        missing: list[str] = []
        for name in cls.required_settings():
            value = getattr(cls, name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(name)

        if getattr(cls, "STORAGE_BACKEND", "local") == "s3":
            for name in (
                "STORAGE_BUCKET",
                "STORAGE_REGION",
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
            ):
                value = getattr(cls, name, None)
                if value is None or (isinstance(value, str) and not value.strip()):
                    if name not in missing:
                        missing.append(name)

        return missing

    @classmethod
    def validate(cls) -> None:
        cls.refresh_from_env()
        missing = cls._missing_settings()
        if not missing:
            return

        env_vars = [_SETTING_ENV_MAP.get(name, name) for name in missing]
        message = (
            f"Missing required configuration for {cls.__name__}: "
            f"{', '.join(missing)}. "
            f"Set environment variable(s): {', '.join(env_vars)}"
        )
        raise ConfigurationError(message)


class DevelopmentConfig(BaseConfig):
    DEBUG = True

    @classmethod
    def refresh_from_env(cls) -> None:
        super().refresh_from_env()
        cls.SECRET_KEY = _env("SECRET_KEY", "dev-secret-change-me")
        cls.JWT_SECRET = _env("JWT_SECRET", "dev-jwt-secret-change-me")
        cls.SQLALCHEMY_DATABASE_URI = _env(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/business_creator",
        )
        cls.FRONTEND_URL = _env("FRONTEND_URL", "http://localhost:3000")
        cls.LOG_JSON = _env_bool("LOG_JSON", False)


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True

    @classmethod
    def refresh_from_env(cls) -> None:
        cls.SECRET_KEY = "test-secret"
        cls.JWT_SECRET = "test-jwt-secret-with-minimum-32-byte-length"
        cls.SQLALCHEMY_DATABASE_URI = _env(
            "TEST_DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/business_creator_test",
        )
        cls.REDIS_URL = _env("TEST_REDIS_URL", "redis://localhost:6379/1")
        cls.CELERY_BROKER_URL = cls.REDIS_URL
        cls.CELERY_RESULT_BACKEND = cls.REDIS_URL
        cls.FRONTEND_URL = "http://localhost:3000"
        cls.LOG_DIR = _env("LOG_DIR", "logs")
        cls.LOG_LEVEL = _env("LOG_LEVEL", "INFO")
        cls.LOG_JSON = False

    @classmethod
    def required_settings(cls) -> tuple[str, ...]:
        return ("SQLALCHEMY_DATABASE_URI", "REDIS_URL")


class StagingConfig(BaseConfig):
    DEBUG = False

    @classmethod
    def required_settings(cls) -> tuple[str, ...]:
        return ProductionConfig.required_settings()


class ProductionConfig(BaseConfig):
    DEBUG = False

    @classmethod
    def required_settings(cls) -> tuple[str, ...]:
        return (
            "SQLALCHEMY_DATABASE_URI",
            "REDIS_URL",
            "SECRET_KEY",
            "JWT_SECRET",
            "WHATSAPP_PHONE_NUMBER_ID",
            "WHATSAPP_ACCESS_TOKEN",
            "WHATSAPP_VERIFY_TOKEN",
            "META_APP_SECRET",
            "AI_API_KEY",
            "FRONTEND_URL",
        )


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "staging": StagingConfig,
    "production": ProductionConfig,
}


def get_config_name() -> str:
    return os.environ.get("FLASK_ENV", "development")
