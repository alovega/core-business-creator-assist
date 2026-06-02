from __future__ import annotations

import re
from datetime import UTC, datetime

from app.common.db_errors import is_unique_violation
from app.customers.models import Customer
from app.customers.validators import normalize_tags


def _utcnow_naive() -> datetime:
    # Keep naive UTC to match existing DB column type expectations.
    return datetime.now(UTC).replace(tzinfo=None)


def normalize_phone_number(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("+"):
        digits = re.sub(r"[^\d]", "", value)
        return f"+{digits}" if digits else ""
    digits = re.sub(r"[^\d]", "", value)
    return f"+{digits}" if digits else ""


def create_customer(*, business, actor, data: dict):
    normalized_phone = normalize_phone_number(data.get("phone_number") or "")
    existing = Customer.get(
        business=business,
        normalized_phone_number=normalized_phone,
    )
    if existing is not None:
        raise ValueError("Customer already exists for this phone number")

    now = _utcnow_naive()
    tags = normalize_tags(data.get("tags"))

    try:
        return Customer(
            business=business,
            name=data["name"].strip(),
            phone_number=data["phone_number"].strip(),
            normalized_phone_number=normalized_phone,
            email=(data.get("email") or "").strip().lower() or None,
            source=(data.get("source") or "manual").strip().lower(),
            tags_json=tags,
            notes=(data.get("notes") or "").strip() or None,
            status=(data.get("status") or "active").strip().lower(),
            created_by=actor,
            updated_by=actor,
            created_at=now,
            updated_at=now,
        )
    except Exception as exc:
        if is_unique_violation(exc):
            raise ValueError("Customer already exists for this phone number")
        raise


def get_customer_for_business(*, customer_id: int, business):
    return Customer.get(id=customer_id, business=business)


def update_customer(*, customer, actor, data: dict):
    if "name" in data and data.get("name") is not None:
        customer.name = data["name"].strip()
    if "phone_number" in data and data.get("phone_number") is not None:
        customer.phone_number = data["phone_number"].strip()
        customer.normalized_phone_number = normalize_phone_number(data["phone_number"])
    if "email" in data:
        email = data.get("email")
        customer.email = email.strip().lower() if isinstance(email, str) and email.strip() else None
    if "source" in data and data.get("source") is not None:
        customer.source = data["source"].strip().lower()
    if "tags" in data:
        customer.tags_json = normalize_tags(data.get("tags"))
    if "notes" in data:
        notes = data.get("notes")
        customer.notes = notes.strip() if isinstance(notes, str) and notes.strip() else None
    if "status" in data and data.get("status") is not None:
        customer.status = data["status"].strip().lower()
    customer.updated_by = actor
    customer.updated_at = _utcnow_naive()
    return customer


def soft_delete_customer(*, customer, actor):
    customer.status = "deleted"
    customer.updated_by = actor
    customer.updated_at = _utcnow_naive()
    return customer


def list_customers(*, business, page: int = 1, per_page: int = 20):
    page = max(1, page)
    per_page = min(100, max(1, per_page))
    offset = (page - 1) * per_page

    scoped = [
        customer
        for customer in Customer.select()
        if customer.business.id == business.id and customer.status != "deleted"
    ]
    scoped.sort(key=lambda customer: customer.created_at, reverse=True)
    total = len(scoped)
    customers = scoped[offset : offset + per_page]
    return customers, total


def search_customers(*, business, q: str | None = None, filters: dict | None = None):
    filters = filters or {}
    term = (q or "").strip().lower()
    normalized_term = normalize_phone_number(q or "")
    source = (filters.get("source") or "").strip().lower()
    status = (filters.get("status") or "").strip().lower()
    tag = (filters.get("tag") or "").strip().lower()

    candidates = [
        customer
        for customer in Customer.select()
        if customer.business.id == business.id and customer.status != "deleted"
    ]
    candidates.sort(key=lambda customer: customer.created_at, reverse=True)

    def _matches(customer) -> bool:
        if source and customer.source != source:
            return False
        if status and customer.status != status:
            return False
        if tag and tag not in [str(t).lower() for t in (customer.tags_json or [])]:
            return False
        if not term:
            return True

        name = (customer.name or "").lower()
        email = (customer.email or "").lower()
        phone = (customer.phone_number or "").lower()
        normalized_phone = (customer.normalized_phone_number or "").lower()
        return (
            term in name
            or term in email
            or term in phone
            or term in normalized_phone
            or (normalized_term and normalized_term in normalized_phone)
        )

    return [customer for customer in candidates if _matches(customer)]


def find_or_create_whatsapp_customer(
    *,
    business,
    phone_number: str,
    profile_name: str | None,
):
    normalized_phone = normalize_phone_number(phone_number)
    customer = Customer.get(
        business=business,
        normalized_phone_number=normalized_phone,
    )
    if customer is not None:
        return customer, False

    now = _utcnow_naive()
    try:
        customer = Customer(
            business=business,
            name=(profile_name or phone_number or "WhatsApp Customer").strip(),
            phone_number=phone_number.strip(),
            normalized_phone_number=normalized_phone,
            source="whatsapp",
            tags_json=[],
            status="active",
            created_at=now,
            updated_at=now,
        )
        return customer, True
    except Exception as exc:
        if not is_unique_violation(exc):
            raise
        existing = Customer.get(
            business=business,
            normalized_phone_number=normalized_phone,
        )
        if existing is None:
            raise
        return existing, False


def related_records(*, customer):
    # Placeholder hooks until those modules are implemented.
    return {
        "conversations": [],
        "leads": [],
        "bookings": [],
        "payments": [],
    }
