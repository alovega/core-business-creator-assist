from flask import g, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.businesses import businesses_bp
from app.businesses.models import Business
from app.businesses.services import merge_settings, slugify, unique_slug
from app.common.auth import require_auth
from app.common.tenant import require_business
from app.extensions import db

UPDATABLE_FIELDS = frozenset(
    {"name", "phone_number", "email", "industry", "plan", "status"}
)


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


@businesses_bp.post("")
@require_auth
def create_business():
    if g.current_user.business_id is not None:
        return jsonify({"error": "User already belongs to a business"}), 409

    data = _json_body()
    name = (data.get("name") or "").strip()
    if not name:
        return _validation_error("Name is required")

    base_slug = slugify(name)
    business = Business(
        name=name,
        slug=unique_slug(base_slug),
        phone_number=(data.get("phone_number") or "").strip() or None,
        email=(data.get("email") or "").strip().lower() or None,
        industry=(data.get("industry") or "").strip() or None,
        plan=(data.get("plan") or "free").strip() or "free",
        status="active",
        settings_json={},
    )
    db.session.add(business)
    try:
        db.session.flush()
        g.current_user.business_id = business.id
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Could not create business"}), 409

    return jsonify({"business": business.to_dict()}), 201


@businesses_bp.get("/current")
@require_auth
@require_business
def get_current_business():
    return jsonify({"business": g.current_business.to_dict()}), 200


@businesses_bp.patch("/current")
@require_auth
@require_business
def update_current_business():
    data = _json_body()
    business = g.current_business

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return _validation_error("Name cannot be empty")
        business.name = name

    for field in UPDATABLE_FIELDS - {"name"}:
        if field not in data:
            continue
        value = data.get(field)
        if value is None:
            setattr(business, field, None)
            continue
        if not isinstance(value, str):
            return _validation_error(f"{field} must be a string")
        value = value.strip()
        if field == "email":
            value = value.lower()
        setattr(business, field, value or None)

    db.session.commit()
    return jsonify({"business": business.to_dict()}), 200


@businesses_bp.get("/current/settings")
@require_auth
@require_business
def get_current_settings():
    return jsonify({"settings": g.current_business.settings_json or {}}), 200


@businesses_bp.patch("/current/settings")
@require_auth
@require_business
def update_current_settings():
    data = _json_body()
    incoming = data.get("settings")
    if incoming is None:
        return _validation_error("settings object is required")
    if not isinstance(incoming, dict):
        return _validation_error("settings must be an object")

    business = g.current_business
    business.settings_json = merge_settings(business.settings_json, incoming)
    db.session.commit()
    return jsonify({"settings": business.settings_json}), 200
