from flask import g, jsonify, request
from pony.orm import commit, db_session

from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.db_errors import is_unique_violation
from app.common.rbac.permissions import PermissionKey
from app.customers import customers_bp
from app.customers.services import (
    create_customer,
    find_or_create_whatsapp_customer,
    get_customer_for_business,
    list_customers,
    related_records,
    search_customers,
    soft_delete_customer,
    update_customer,
)
from app.customers.validators import (
    serialize_customer,
    validate_create_customer_fields,
    validate_update_customer_fields,
)


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_errors(errors: dict[str, str]):
    if len(errors) == 1:
        message = next(iter(errors.values()))
    else:
        message = "Please correct the errors below."
    return jsonify({"error": message, "errors": errors}), 400


@customers_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def list_customers_route():
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", 20, type=int) or 20
    customers, total = list_customers(
        business=g.current_business,
        page=page,
        per_page=per_page,
    )
    return (
        jsonify(
            {
                "customers": [serialize_customer(customer) for customer in customers],
                "page": page,
                "per_page": per_page,
                "total": total,
            }
        ),
        200,
    )


@customers_bp.post("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CUSTOMERS)
@db_session
def create_customer_route():
    data = _json_body()
    errors = validate_create_customer_fields(data)
    if errors:
        return _validation_errors(errors)
    try:
        customer = create_customer(
            business=g.current_business,
            actor=g.current_user,
            data=data,
        )
        commit()
        return jsonify({"customer": serialize_customer(customer)}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        if is_unique_violation(exc):
            return jsonify({"error": "Customer already exists for this phone number"}), 409
        raise


@customers_bp.get("/search")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def search_customers_route():
    q = request.args.get("q")
    results = search_customers(
        business=g.current_business,
        q=q,
        filters={
            "tag": request.args.get("tag"),
            "source": request.args.get("source"),
            "status": request.args.get("status"),
        },
    )
    return jsonify({"customers": [serialize_customer(customer) for customer in results]}), 200


@customers_bp.get("/<int:customer_id>")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def get_customer_route(customer_id: int):
    customer = get_customer_for_business(
        customer_id=customer_id,
        business=g.current_business,
    )
    if customer is None or customer.status == "deleted":
        return jsonify({"error": "Customer not found"}), 404
    return jsonify({"customer": serialize_customer(customer)}), 200


@customers_bp.patch("/<int:customer_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CUSTOMERS)
@db_session
def update_customer_route(customer_id: int):
    customer = get_customer_for_business(
        customer_id=customer_id,
        business=g.current_business,
    )
    if customer is None or customer.status == "deleted":
        return jsonify({"error": "Customer not found"}), 404

    data = _json_body()
    errors = validate_update_customer_fields(data)
    if errors:
        return _validation_errors(errors)
    try:
        updated = update_customer(customer=customer, actor=g.current_user, data=data)
        commit()
        return jsonify({"customer": serialize_customer(updated)}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        if is_unique_violation(exc):
            return jsonify({"error": "Customer already exists for this phone number"}), 409
        raise


@customers_bp.delete("/<int:customer_id>")
@login_required
@business_required
@permission_required(PermissionKey.DELETE_CUSTOMERS)
@db_session
def delete_customer_route(customer_id: int):
    customer = get_customer_for_business(
        customer_id=customer_id,
        business=g.current_business,
    )
    if customer is None or customer.status == "deleted":
        return jsonify({"error": "Customer not found"}), 404
    soft_delete_customer(customer=customer, actor=g.current_user)
    commit()
    return jsonify({"message": "Customer deleted"}), 200


@customers_bp.get("/<int:customer_id>/conversations")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def customer_conversations_route(customer_id: int):
    customer = get_customer_for_business(
        customer_id=customer_id,
        business=g.current_business,
    )
    if customer is None or customer.status == "deleted":
        return jsonify({"error": "Customer not found"}), 404
    return jsonify({"conversations": related_records(customer=customer)["conversations"]}), 200


@customers_bp.get("/<int:customer_id>/leads")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def customer_leads_route(customer_id: int):
    customer = get_customer_for_business(
        customer_id=customer_id,
        business=g.current_business,
    )
    if customer is None or customer.status == "deleted":
        return jsonify({"error": "Customer not found"}), 404
    return jsonify({"leads": related_records(customer=customer)["leads"]}), 200


@customers_bp.get("/<int:customer_id>/bookings")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def customer_bookings_route(customer_id: int):
    customer = get_customer_for_business(
        customer_id=customer_id,
        business=g.current_business,
    )
    if customer is None or customer.status == "deleted":
        return jsonify({"error": "Customer not found"}), 404
    return jsonify({"bookings": related_records(customer=customer)["bookings"]}), 200


@customers_bp.get("/<int:customer_id>/payments")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CUSTOMERS)
@db_session
def customer_payments_route(customer_id: int):
    customer = get_customer_for_business(
        customer_id=customer_id,
        business=g.current_business,
    )
    if customer is None or customer.status == "deleted":
        return jsonify({"error": "Customer not found"}), 404
    return jsonify({"payments": related_records(customer=customer)["payments"]}), 200


@customers_bp.post("/resolve/whatsapp")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CUSTOMERS)
@db_session
def resolve_whatsapp_customer_route():
    data = _json_body()
    phone_number = (data.get("phone_number") or "").strip()
    profile_name = (data.get("profile_name") or "").strip() or None
    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    customer, created = find_or_create_whatsapp_customer(
        business=g.current_business,
        phone_number=phone_number,
        profile_name=profile_name,
    )
    commit()
    return jsonify({"customer": serialize_customer(customer), "created": created}), 200
