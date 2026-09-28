from __future__ import annotations

import os
import re
from datetime import datetime

from pony.orm import commit

from app.customers.models import Customer


def normalize_phone_number(phone_number: str) -> str:
    """Return a stable digits-only representation suitable for tenant-scoped lookup.

    E.164 numbers remain international. Local numbers beginning with 0 use the
    configurable DEFAULT_PHONE_COUNTRY_CODE (254 by default for this deployment).
    """
    if not isinstance(phone_number, str) or not phone_number.strip():
        raise ValueError("phone_number is required")

    value = phone_number.strip()
    value = re.sub(r"[\s().-]", "", value)

    if value.startswith("+"):
        value = value[1:]
    elif value.startswith("00"):
        value = value[2:]
    elif value.startswith("0"):
        country_code = os.getenv("DEFAULT_PHONE_COUNTRY_CODE", "254").strip().lstrip("+")
        if not country_code.isdigit():
            raise ValueError("DEFAULT_PHONE_COUNTRY_CODE must contain digits only")
        value = country_code + value[1:]

    if not value.isdigit():
        raise ValueError("phone_number contains invalid characters")
    if not 8 <= len(value) <= 15:
        raise ValueError("phone_number must contain between 8 and 15 digits")
    return value


def find_customer_by_phone(*, business, phone_number: str) -> Customer | None:
    normalized = normalize_phone_number(phone_number)
    return Customer.get(
        business=business,
        normalized_phone_number=normalized,
    )


def get_or_create_customer_from_whatsapp(
    *,
    business,
    phone_number: str,
    name: str | None = None,
) -> tuple[Customer, bool]:
    """Idempotently resolve an inbound WhatsApp sender to a business customer.

    This is intentionally independent of Flask request state so the WhatsApp
    webhook/worker can call it after resolving the destination business.
    """
    normalized = normalize_phone_number(phone_number)
    customer = Customer.get(
        business=business,
        normalized_phone_number=normalized,
    )
    if customer is not None:
        changed = False
        if name and not customer.name:
            customer.name = name.strip() or None
            changed = True
        if changed:
            customer.updated_at = datetime.utcnow()
            commit()
        return customer, False

    customer = Customer(
        business=business,
        name=name.strip() if isinstance(name, str) and name.strip() else None,
        phone_number=phone_number.strip(),
        normalized_phone_number=normalized,
        source="whatsapp",
        tags_json=[],
        status="active",
    )
    commit()
    return customer, True