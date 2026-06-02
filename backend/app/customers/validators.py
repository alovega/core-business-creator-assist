from __future__ import annotations

from datetime import datetime

ALLOWED_SOURCES = frozenset({"manual", "whatsapp", "import", "api"})
ALLOWED_STATUSES = frozenset({"active", "archived", "deleted"})


def _clean_optional_string(value, *, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if max_len is not None:
        stripped = stripped[:max_len]
    return stripped


def validate_create_customer_fields(data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    name = data.get("name")
    phone = data.get("phone_number")
    if not isinstance(name, str) or not name.strip():
        errors["name"] = "Name is required"
    if not isinstance(phone, str) or not phone.strip():
        errors["phone_number"] = "Phone number is required"

    email = data.get("email")
    if email is not None and (not isinstance(email, str) or not email.strip()):
        errors["email"] = "Email must be a non-empty string"

    source = data.get("source")
    if source is not None:
        if not isinstance(source, str) or not source.strip():
            errors["source"] = "Source must be a non-empty string"
        elif source.strip().lower() not in ALLOWED_SOURCES:
            errors["source"] = f"Source must be one of: {', '.join(sorted(ALLOWED_SOURCES))}"

    status = data.get("status")
    if status is not None:
        if not isinstance(status, str) or not status.strip():
            errors["status"] = "Status must be a non-empty string"
        elif status.strip().lower() not in ALLOWED_STATUSES:
            errors["status"] = (
                f"Status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"
            )

    tags = data.get("tags")
    if tags is not None:
        if not isinstance(tags, list):
            errors["tags"] = "Tags must be an array of strings"
        else:
            invalid = [t for t in tags if not isinstance(t, str)]
            if invalid:
                errors["tags"] = "Tags must be an array of strings"

    return errors


def validate_update_customer_fields(data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not data:
        errors["_form"] = "At least one field is required"
        return errors

    if "name" in data and (not isinstance(data.get("name"), str) or not data["name"].strip()):
        errors["name"] = "Name must be a non-empty string"

    if "phone_number" in data and (
        not isinstance(data.get("phone_number"), str) or not data["phone_number"].strip()
    ):
        errors["phone_number"] = "Phone number must be a non-empty string"

    if "email" in data and data.get("email") is not None:
        if not isinstance(data.get("email"), str):
            errors["email"] = "Email must be a string or null"

    if "source" in data and data.get("source") is not None:
        source = data["source"]
        if not isinstance(source, str) or not source.strip():
            errors["source"] = "Source must be a non-empty string"
        elif source.strip().lower() not in ALLOWED_SOURCES:
            errors["source"] = f"Source must be one of: {', '.join(sorted(ALLOWED_SOURCES))}"

    if "status" in data and data.get("status") is not None:
        status = data["status"]
        if not isinstance(status, str) or not status.strip():
            errors["status"] = "Status must be a non-empty string"
        elif status.strip().lower() not in ALLOWED_STATUSES:
            errors["status"] = (
                f"Status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"
            )

    if "tags" in data and data.get("tags") is not None:
        tags = data["tags"]
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            errors["tags"] = "Tags must be an array of strings"

    return errors


def normalize_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    if not tags:
        return cleaned
    seen: set[str] = set()
    for raw in tags:
        tag = raw.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag)
    return cleaned


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"


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
        "created_by_id": customer.created_by.id if customer.created_by else None,
        "updated_by_id": customer.updated_by.id if customer.updated_by else None,
        "created_at": serialize_datetime(customer.created_at),
        "updated_at": serialize_datetime(customer.updated_at),
    }
