"""Database error helpers."""


def is_unique_violation(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message
