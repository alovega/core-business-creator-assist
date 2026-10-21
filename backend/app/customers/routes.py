from __future__ import annotations

from datetime import datetime

from flask import g, jsonify, request
from pony.orm import commit, db_session, select

from app.bookings.models import Booking
from app.common.db_errors import is_unique_violation
from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.conversations.models import Conversation
from app.customers import customers_bp
from app.customers.models import Customer, VALID_CUSTOMER_SOURCES, VALID_CUSTOMER_STATUSES
from app.customers.services import normalize_phone_number
from app.customers.validators import (
    serialize_customer,
    validate_create_customer,
    validate_update_customer,
)
from app.leads.models import Lead


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _customer_for_current_business(customer_id: int) -> Customer | None:
    return Customer.get(id=customer_id, business=g.current_business)


def _parse_positive_int(value, field: str, *, default: int, maximum: int | None = None) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{field} must be greater than 0")
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def _customer_conflict(normalized_phone_number: str, *, exclude_id: int | None = None):
    customer = Customer.get(
        business=g.current_business,
        normalized_phone_number=normalized_phone_number,
    )
    if customer is None or customer.id == exclude_id:
        return None
    return customer


def _list_customers_response():
    try:
        page = _parse_positive_int(request.args.get("page"), "page", default=1)
        per_page = _parse_positive_int(
            request.args.get("per_page"), "per_page", default=50, maximum=100
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    status = (request.args.get("status") or "").strip().lower()
    source = (request.args.get("source") or "").strip().lower()
    tag = (request.args.get("tag") or "").strip().casefold()
    q = (request.args.get("q") or "").strip().casefold()

    if status and status not in VALID_CUSTOMER_STATUSES:
        return jsonify({"error": "Invalid customer status"}), 400
    if source and source not in VALID_CUSTOMER_SOURCES:
        return jsonify({"error": "Invalid customer source"}), 400

    customers = sorted(
        list(select(c for c in Customer if c.business == g.current_business)),
        key=lambda c: c.created_at,
        reverse=True,
    )

    if status:
        customers = [c for c in customers if c.status == status]
    if source:
        customers = [c for c in customers if c.source == source]
    if tag:
        customers = [
            c
            for c in customers
            if any(str(item).casefold() == tag for item in (c.tags_json or []))
        ]
    if q:
        customers = [
            c
            for c in customers
            if q in (c.name or "").casefold()
            or q in (c.email or "").casefold()
            or q in c.phone_number.casefold()
            or q in c.normalized_phone_number.casefold()
            or any(q in str(item).casefold() for item in (c.tags_json or []))
            or q in c.source.casefold()
            or q in c.status.casefold()
        ]

    total = len(customers)
    start = (page - 1) * per_page
    end = start + per_page
    items = customers[start:end]

    return jsonify(
        {
            "customers": [serialize_customer(customer) for customer in items],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page if total else 0,
            },
        }
    ), 200


@customers_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def list_customers():
    return _list_customers_response()


@customers_bp.get("/search")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def search_customers():
    return _list_customers_response()


@customers_bp.post("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CUSTOMERS)
@db_session
def create_customer():
    cleaned, errors = validate_create_customer(_json_body(), normalize_phone_number)
    if errors:
        return jsonify({"error": "Validation failed", "errors": errors}), 400

    if _customer_conflict(cleaned["normalized_phone_number"]):
        return jsonify({"error": "A customer with this phone number already exists"}), 409

    customer = Customer(
        business=g.current_business,
        name=cleaned.get("name"),
        phone_number=cleaned["phone_number"],
        normalized_phone_number=cleaned["normalized_phone_number"],
        email=cleaned.get("email"),
        source=cleaned["source"],
        tags_json=cleaned["tags"],
        notes=cleaned.get("notes"),
        status=cleaned["status"],
        created_by=g.current_user,
        updated_by=g.current_user,
    )
    try:
        commit()
    except Exception as exc:
        if is_unique_violation(exc):
            return jsonify({"error": "A customer with this phone number already exists"}), 409
        raise
    return jsonify({"customer": serialize_customer(customer)}), 201


@customers_bp.get("/<int:customer_id>")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def get_customer(customer_id: int):
    customer = _customer_for_current_business(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404
    return jsonify({"customer": serialize_customer(customer)}), 200


@customers_bp.patch("/<int:customer_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CUSTOMERS)
@db_session
def update_customer(customer_id: int):
    customer = _customer_for_current_business(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404

    cleaned, errors = validate_update_customer(_json_body(), normalize_phone_number)
    if errors:
        return jsonify({"error": "Validation failed", "errors": errors}), 400

    if "normalized_phone_number" in cleaned and _customer_conflict(
        cleaned["normalized_phone_number"], exclude_id=customer.id
    ):
        return jsonify({"error": "A customer with this phone number already exists"}), 409

    if "name" in cleaned:
        customer.name = cleaned["name"]
    if "phone_number" in cleaned:
        customer.phone_number = cleaned["phone_number"]
        customer.normalized_phone_number = cleaned["normalized_phone_number"]
    if "email" in cleaned:
        customer.email = cleaned["email"]
    if "source" in cleaned:
        customer.source = cleaned["source"]
    if "tags" in cleaned:
        customer.tags_json = cleaned["tags"]
    if "notes" in cleaned:
        customer.notes = cleaned["notes"]
    if "status" in cleaned:
        customer.status = cleaned["status"]

    customer.updated_by = g.current_user
    customer.updated_at = datetime.utcnow()
    try:
        commit()
    except Exception as exc:
        if is_unique_violation(exc):
            return jsonify({"error": "A customer with this phone number already exists"}), 409
        raise
    return jsonify({"customer": serialize_customer(customer)}), 200


@customers_bp.delete("/<int:customer_id>")
@login_required
@business_required
@permission_required(PermissionKey.DELETE_CUSTOMERS)
@db_session
def delete_customer(customer_id: int):
    customer = _customer_for_current_business(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404

    has_conversations = Conversation.exists(
        business=g.current_business, customer_id=customer.id
    )
    has_leads = Lead.exists(business=g.current_business, customer_id=customer.id)
    has_bookings = Booking.exists(business=g.current_business, customer_id=customer.id)

    if has_conversations or has_leads or has_bookings:
        return jsonify(
            {"error": "Customer cannot be deleted while related records exist"}
        ), 409

    customer.delete()
    commit()
    return "", 204


@customers_bp.get("/<int:customer_id>/conversations")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def customer_conversations(customer_id: int):
    customer = _customer_for_current_business(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404
    items = sorted(
        list(
            select(
                item
                for item in Conversation
                if item.business == g.current_business and item.customer_id == customer.id
            )
        ),
        key=lambda item: item.updated_at,
        reverse=True,
    )
    return jsonify({"conversations": [item.to_dict() for item in items]}), 200


@customers_bp.get("/<int:customer_id>/leads")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def customer_leads(customer_id: int):
    customer = _customer_for_current_business(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404
    items = sorted(
        list(
            select(
                item
                for item in Lead
                if item.business == g.current_business and item.customer_id == customer.id
            )
        ),
        key=lambda item: item.updated_at,
        reverse=True,
    )
    return jsonify({"leads": [item.to_dict() for item in items]}), 200


@customers_bp.get("/<int:customer_id>/bookings")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def customer_bookings(customer_id: int):
    customer = _customer_for_current_business(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404
    items = sorted(
        list(
            select(
                item
                for item in Booking
                if item.business == g.current_business and item.customer_id == customer.id
            )
        ),
        key=lambda item: item.scheduled_at,
        reverse=True,
    )
    return jsonify({"bookings": [item.to_dict() for item in items]}), 200


@customers_bp.get("/<int:customer_id>/payments")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def customer_payments(customer_id: int):
    customer = _customer_for_current_business(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404

    try:
        from app.payments.models import Payment
    except ImportError:
        return jsonify({"payments": []}), 200

    items = sorted(
        list(
            select(
                item
                for item in Payment
                if item.business == g.current_business and item.customer_id == customer.id
            )
        ),
        key=lambda item: item.created_at,
        reverse=True,
    )
    return jsonify({"payments": [item.to_dict() for item in items]}), 200