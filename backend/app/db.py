"""Pony ORM database binding (SolarisServer-style)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from pony.orm import Database

db = Database()
_orm_mapping_complete = False


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes")


def _parse_postgres_url(database_url: str) -> dict:
    parsed = urlparse(database_url)
    return {
        "provider": "postgres",
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": (parsed.path or "/").lstrip("/"),
    }


def ensure_database_ready(database_url: str) -> None:
    """Create PostgreSQL database if missing (Solaris create_db.py)."""
    from app.migrations.create_db import ensure_postgres_database_exists

    ensure_postgres_database_exists(database_url)


def bind_database(database_url: str) -> None:
    if database_url.startswith("sqlite"):
        filename = ":memory:" if ":memory:" in database_url else database_url.removeprefix(
            "sqlite:///"
        )
        db.bind(provider="sqlite", filename=filename, create_db=True)
        return
    db.bind(**_parse_postgres_url(database_url))


def generate_mapping(*, create_tables: bool = False, check_tables: bool = True) -> None:
    # Import entities so Pony registers them before mapping.
    from app.businesses import models as _business_models  # noqa: F401
    from app.common.rbac import models as _rbac_models  # noqa: F401
    from app.users import models as _user_models  # noqa: F401

    db.generate_mapping(create_tables=create_tables, check_tables=check_tables)


def seed_rbac_if_needed() -> None:
    from app.common.rbac.seed import ensure_rbac_seeded

    ensure_rbac_seeded()


def should_auto_migrate() -> bool:
    """Whether to run pending migrations during app startup."""
    if os.environ.get("FLASK_ENV") == "testing":
        return False
    if not _env_flag("RUN_MIGRATIONS", default=True):
        return False
    if _env_flag("SKIP_MIGRATIONS", default=False):
        return False
    return True


def apply_pending_migrations() -> None:
    """Apply pending timestamped migrations (Solaris update.py / migrate.up)."""
    from app.migrations.runner import run_pending_migrations

    print("Applying pending database migrations...")
    previous = os.environ.get("MIGRATE_MODE")
    os.environ["MIGRATE_MODE"] = "1"
    try:
        run_pending_migrations()
    finally:
        if previous is None:
            os.environ.pop("MIGRATE_MODE", None)
        else:
            os.environ["MIGRATE_MODE"] = previous
    print("Database migrations are up to date.")


def init_database(app) -> None:
    database_url = app.config["SQLALCHEMY_DATABASE_URI"]
    testing = app.config.get("TESTING", False)
    install_mode = os.environ.get("INSTALL_MODE") == "1"

    if not testing:
        ensure_database_ready(database_url)
    else:
        if db.provider is not None:
            return
        bind_database(database_url)
        global _orm_mapping_complete
        if not _orm_mapping_complete:
            generate_mapping(create_tables=True, check_tables=False)
            _orm_mapping_complete = True
        seed_rbac_if_needed()
        return

    if db.provider is not None:
        db.disconnect()
    bind_database(database_url)

    generate_mapping(
        create_tables=install_mode,
        check_tables=False,
    )

    if not testing and should_auto_migrate():
        apply_pending_migrations()

    seed_rbac_if_needed()


def bootstrap_database() -> None:
    """Solaris-style startup: ensure DB exists, bind Pony, apply pending migrations."""
    from dotenv import load_dotenv

    from app import create_app

    load_dotenv()
    create_app()


def bootstrap_database_for_cli() -> None:
    """CLI / entrypoint hook (same as bootstrap_database)."""
    bootstrap_database()
