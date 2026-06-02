"""UTC time helpers."""

from datetime import UTC, datetime


def utc_now_naive() -> datetime:
    """Return current UTC time as naive datetime for DB compatibility."""
    return datetime.now(UTC).replace(tzinfo=None)
