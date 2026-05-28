"""Ensure PostgreSQL application databases exist (SolarisServer-style)."""

from __future__ import annotations

import os
import time
from urllib.parse import urlparse


def _postgres_admin_connect_kwargs(database_url: str, *, admin_database: str = "postgres") -> dict:
    parsed = urlparse(database_url)
    return {
        "dbname": admin_database,
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
    }


def database_exists(database_url: str) -> bool:
    """Return True if the target database accepts connections."""
    import psycopg2

    parsed = urlparse(database_url)
    try:
        conn = psycopg2.connect(
            dbname=(parsed.path or "/").lstrip("/"),
            user=parsed.username or "postgres",
            password=parsed.password or "",
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            connect_timeout=10,
        )
        conn.close()
        return True
    except psycopg2.OperationalError:
        return False


def ensure_postgres_database_exists(
    database_url: str,
    *,
    retries: int = 12,
    retry_delay_seconds: int = 5,
) -> None:
    """Create the application database if missing (no-op for SQLite)."""
    if not database_url or database_url.startswith("sqlite"):
        return

    if database_exists(database_url):
        parsed = urlparse(database_url)
        db_name = (parsed.path or "/").lstrip("/")
        print(f'Database "{db_name}" is reachable.')
        return

    import psycopg2

    parsed = urlparse(database_url)
    db_name = (parsed.path or "/").lstrip("/")
    admin_kwargs = _postgres_admin_connect_kwargs(database_url)

    conn = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(connect_timeout=10, **admin_kwargs)
            break
        except psycopg2.OperationalError as exc:
            if attempt == retries:
                raise RuntimeError(
                    f"Could not connect to PostgreSQL at {admin_kwargs['host']}:"
                    f"{admin_kwargs['port']} after {retries} attempts"
                ) from exc
            print(f"Waiting for PostgreSQL ({attempt}/{retries}): {exc}")
            time.sleep(retry_delay_seconds)

    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if cur.fetchone():
                print(f'Database "{db_name}" already exists.')
                return
            print(f'Creating database "{db_name}"...')
            cur.execute(f'CREATE DATABASE "{db_name}"')
            print(f'Database "{db_name}" created.')
    finally:
        conn.close()


def ensure_postgres_database_from_env() -> None:
    """Ensure DATABASE_URL database exists using environment configuration."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/business_creator",
    )
    ensure_postgres_database_exists(database_url)


def _database_name_from_url(database_url: str) -> str:
    return (urlparse(database_url).path or "/").lstrip("/")


def drop_postgres_database(
    database_url: str,
    *,
    allow_non_test: bool = False,
) -> None:
    """Drop a PostgreSQL database if it exists (no-op for SQLite)."""
    if not database_url or database_url.startswith("sqlite"):
        return

    db_name = _database_name_from_url(database_url)
    if not db_name:
        raise ValueError("Database name missing from URL")
    if not allow_non_test and not db_name.endswith("_test"):
        raise ValueError(
            f'Refusing to drop "{db_name}" (only *_test databases are allowed)'
        )

    import psycopg2

    admin_kwargs = _postgres_admin_connect_kwargs(database_url)
    try:
        conn = psycopg2.connect(connect_timeout=10, **admin_kwargs)
    except psycopg2.OperationalError as exc:
        print(f"PostgreSQL unavailable; skipping drop of {db_name!r}: {exc}")
        return

    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not cur.fetchone():
                print(f'Database "{db_name}" does not exist; nothing to drop.')
                return
            print(f'Dropping database "{db_name}"...')
            cur.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (db_name,),
            )
            cur.execute(f'DROP DATABASE "{db_name}"')
            print(f'Database "{db_name}" dropped.')
    finally:
        conn.close()


def drop_test_database_from_env() -> None:
    """Drop TEST_DATABASE_URL database if it exists."""
    database_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/business_creator_test",
    )
    drop_postgres_database(database_url)
