from __future__ import annotations

import re
from typing import Any

from app.customers.models import VALID_CUSTOMER_SOURCES, VALID_CUSTOMER_STATUSES

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_NOTES_LENGTH = 5000


def serialize_customer(customer) -> dict:
    return {
        "id": customer.id,
        "business_id": customer.business.id,
        "name": customer.name,
        "phone_number": customer.phone_number,
        "normalized_phone_number": customer.normalized_phone_number,
        "email": customer.email,
        "source": customer.source,
        "tags": list(customer.tags_json or []),
        "notes": customer.notes,
        "status": customer.status,
        "created_by_user_id": customer.created_by.id if customer.created_by else None,
        "updated_by_user_id": customer.updated_by.id if customer.updated_by else None,
        "created_at": customer.created_at.isoformat() + "Z",
        "updated_at": customer.updated_at.isoformat() + "Z",
    }


def _clean_optional_string(value: Any, field: str, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise ValueError(f"{field} must be {max_length} characters or fewer")
    return cleaned or None


def _clean_email(value: Any) -> str | None:
    email = _clean_optional_string(value, "email", 255)
    if email is None:
        return None
    email = email.lower()
    if not EMAIL_RE.match(email):
        raise ValueError("email must be a valid email address")
    return email


def _clean_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("tags must be an array")

    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("tags must contain only strings")
        tag = item.strip()
        if not tag:
            continue
        if len(tag) > 100:
            raise ValueError("each tag must be 100 characters or fewer")
        key = tag.casefold()
        if key not in seen:
            tags.append(tag)
            seen.add(key)
    return tags


def _clean_choice(value: Any, field: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    cleaned = value.strip().lower()
    if cleaned not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return cleaned


def validate_create_customer(data: dict, normalize_phone) -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    cleaned: dict = {}

    if not isinstance(data, dict):
        return {}, {"body": "Request body must be a JSON object"}

    phone = data.get("phone_number")
    if not isinstance(phone, str) or not phone.strip():
        errors["phone_number"] = "phone_number is required"
    else:
        try:
            cleaned["phone_number"] = phone.strip()
            cleaned["normalized_phone_number"] = normalize_phone(phone)
        except ValueError as exc:
            errors["phone_number"] = str(exc)

    try:
        cleaned["name"] = _clean_optional_string(data.get("name"), "name", 255)
    except ValueError as exc:
        errors["name"] = str(exc)

    try:
        cleaned["email"] = _clean_email(data.get("email"))
    except ValueError as exc:
        errors["email"] = str(exc)

    try:
        cleaned["source"] = _clean_choice(
            data.get("source", "manual"), "source", VALID_CUSTOMER_SOURCES
        )
    except ValueError as exc:
        errors["source"] = str(exc)

    try:
        cleaned["status"] = _clean_choice(
            data.get("status", "active"), "status", VALID_CUSTOMER_STATUSES
        )
    except ValueError as exc:
        errors["status"] = str(exc)

    try:
        cleaned["tags"] = _clean_tags(data.get("tags", []))
    except ValueError as exc:
        errors["tags"] = str(exc)

    try:
        cleaned["notes"] = _clean_optional_string(
            data.get("notes"), "notes", MAX_NOTES_LENGTH
        )
    except ValueError as exc:
        errors["notes"] = str(exc)

    return cleaned, errors


def validate_update_customer(data: dict, normalize_phone) -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    cleaned: dict = {}

    if not isinstance(data, dict):
        return {}, {"body": "Request body must be a JSON object"}

    if "phone_number" in data:
        phone = data.get("phone_number")
        if not isinstance(phone, str) or not phone.strip():
            errors["phone_number"] = "phone_number is required"
        else:
            try:
                cleaned["phone_number"] = phone.strip()
                cleaned["normalized_phone_number"] = normalize_phone(phone)
            except ValueError as exc:
                errors["phone_number"] = str(exc)

    if "name" in data:
        try:
            cleaned["name"] = _clean_optional_string(data.get("name"), "name", 255)
        except ValueError as exc:
            errors["name"] = str(exc)

    if "email" in data:
        try:
            cleaned["email"] = _clean_email(data.get("email"))
        except ValueError as exc:
            errors["email"] = str(exc)

    if "source" in data:
        try:
            cleaned["source"] = _clean_choice(
                data.get("source"), "source", VALID_CUSTOMER_SOURCES
            )
        except ValueError as exc:
            errors["source"] = str(exc)

    if "status" in data:
        try:
            cleaned["status"] = _clean_choice(
                data.get("status"), "status", VALID_CUSTOMER_STATUSES
            )
        except ValueError as exc:
            errors["status"] = str(exc)

    if "tags" in data:
        try:
            cleaned["tags"] = _clean_tags(data.get("tags"))
        except ValueError as exc:
            errors["tags"] = str(exc)

    if "notes" in data:
        try:
            cleaned["notes"] = _clean_optional_string(
                data.get("notes"), "notes", MAX_NOTES_LENGTH
            )
        except ValueError as exc:
            errors["notes"] = str(exc)

    return cleaned, errors