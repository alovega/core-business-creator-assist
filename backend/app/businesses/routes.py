from flask import current_app, g, jsonify, request
from pony.orm import commit, db_session

from app.businesses import businesses_bp
from app.auth.services import create_access_token
from app.businesses.membership_service import (
    create_owner_membership,
    get_membership,
    get_membership_by_id,
    invite_member,
    list_accessible_businesses,
    list_business_members,
    remove_member,
    switch_workspace,
    update_member_role,
)
from app.businesses.membership_status import MembershipStatus
from app.businesses.models import Business
from app.businesses.services import merge_settings, slugify, unique_slug
from app.businesses.validators import (
    validate_create_business_fields,
    validate_invite_member_fields,
    validate_update_member_fields,
)
from app.common.db_errors import is_unique_violation
from app.common.rbac.access import owner_only_setting_keys, permission_denied
from app.common.rbac.decorators import (
    business_required,
    login_required,
    permission_required,
    user_has_permission,
)
from app.common.rbac.permissions import (
    OWNER_ONLY_SETTING_KEYS,
    PermissionKey,
    is_owner_membership,
    membership_has_permission,
)
from app.common.rbac.roles import Role
from app.users.models import User

UPDATABLE_FIELDS = frozenset(
    {"name", "phone_number", "email", "industry", "plan", "status"}
)
OWNER_ONLY_BUSINESS_FIELDS = frozenset({"plan", "status"})


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


def _validation_errors(field_errors: dict[str, str]):
    if len(field_errors) == 1:
        message = next(iter(field_errors.values()))
    else:
        message = "Please correct the errors below."
    return jsonify({"error": message, "errors": field_errors}), 400


def _filter_owner_settings(settings: dict) -> dict:
    membership = g.current_membership
    if is_owner_membership(membership):
        return settings
    return {k: v for k, v in settings.items() if k not in OWNER_ONLY_SETTING_KEYS}


@businesses_bp.post("")
@login_required
@db_session
def create_business():
    data = _json_body()
    field_errors = validate_create_business_fields(
        data,
        owner_email=g.current_user.email,
    )
    if field_errors:
        return _validation_errors(field_errors)

    name = data["name"].strip()
    email = g.current_user.email.strip().lower()
    phone_number = data["phone_number"].strip()
    industry = data["industry"].strip()
    plan_raw = data.get("plan")
    plan = (
        plan_raw.strip().lower()
        if isinstance(plan_raw, str) and plan_raw.strip()
        else "free"
    )

    base_slug = slugify(name)
    business = Business(
        name=name,
        slug=unique_slug(base_slug),
        phone_number=phone_number,
        email=email,
        industry=industry,
        plan=plan,
        status="active",
        settings_json={},
    )
    membership = create_owner_membership(g.current_user, business)
    try:
        commit()
    except Exception as exc:
        if is_unique_violation(exc):
            return jsonify({"error": "Could not create business"}), 409
        raise

    token, _ = create_access_token(
        g.current_user.id,
        current_app.config["JWT_SECRET"],
        current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        business_id=business.id,
    )
    return (
        jsonify(
            {
                "business": business.to_dict(),
                "membership": membership.to_dict(include_user=False),
                "access_token": token,
            }
        ),
        201,
    )


@businesses_bp.get("")
@login_required
@db_session
def list_businesses():
    businesses = list_accessible_businesses(g.current_user)
    return jsonify({"businesses": businesses}), 200


@businesses_bp.post("/switch")
@login_required
@db_session
def switch_business():
    data = _json_body()
    business_id = data.get("business_id")
    if business_id is None:
        return _validation_error("business_id is required")
    try:
        business_id = int(business_id)
    except (TypeError, ValueError):
        return _validation_error("business_id must be an integer")

    try:
        business = switch_workspace(g.current_user, business_id)
        commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 403

    membership = g.current_user.active_membership_for(business.id)
    token, _ = create_access_token(
        g.current_user.id,
        current_app.config["JWT_SECRET"],
        current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        business_id=business.id,
    )
    return (
        jsonify(
            {
                "business": business.to_dict(),
                "membership": membership.to_dict(include_user=False) if membership else None,
                "access_token": token,
            }
        ),
        200,
    )


@businesses_bp.get("/<int:business_id>")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_DASHBOARD)
def get_business_by_id(business_id: int):
    return jsonify({"business": g.current_business.to_dict()}), 200


@businesses_bp.get("/current")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_DASHBOARD)
def get_current_business():
    return jsonify({"business": g.current_business.to_dict()}), 200


@businesses_bp.patch("/current")
@login_required
@business_required
@db_session
def update_current_business():
    data = _json_body()
    business = g.current_business
    membership = g.current_membership

    restricted = OWNER_ONLY_BUSINESS_FIELDS & data.keys()
    if restricted and not is_owner_membership(membership):
        fields = ", ".join(sorted(restricted))
        return permission_denied(
            f"You do not have permission to update owner-only fields: {fields}"
        )

    if not membership_has_permission(membership, PermissionKey.MANAGE_BUSINESS_SETTINGS):
        return permission_denied(permission=PermissionKey.MANAGE_BUSINESS_SETTINGS.value)

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

    commit()
    return jsonify({"business": business.to_dict()}), 200


@businesses_bp.get("/current/settings")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_DASHBOARD)
def get_current_settings():
    raw = g.current_business.settings_json or {}
    settings = _filter_owner_settings(raw)
    return jsonify({"settings": settings}), 200


@businesses_bp.patch("/current/settings")
@login_required
@business_required
@db_session
def update_current_settings():
    data = _json_body()
    incoming = data.get("settings")
    if incoming is None:
        return _validation_error("settings object is required")
    if not isinstance(incoming, dict):
        return _validation_error("settings must be an object")

    membership = g.current_membership
    restricted = owner_only_setting_keys(incoming)
    if restricted and not is_owner_membership(membership):
        keys = ", ".join(sorted(restricted))
        return permission_denied(
            f"You do not have permission to update owner-only settings: {keys}"
        )

    if not membership_has_permission(membership, PermissionKey.MANAGE_BUSINESS_SETTINGS):
        return permission_denied(permission=PermissionKey.MANAGE_BUSINESS_SETTINGS.value)

    business = g.current_business
    business.settings_json = merge_settings(business.settings_json, incoming)
    commit()

    visible = _filter_owner_settings(business.settings_json or {})
    return jsonify({"settings": visible}), 200


@businesses_bp.get("/current/members")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_MEMBERS)
@db_session
def list_members():
    members = list_business_members(g.current_business)
    return jsonify({"members": [m.to_dict() for m in members]}), 200


@businesses_bp.post("/current/members/invite")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_MEMBERS)
@db_session
def invite_business_member():
    data = _json_body()
    field_errors = validate_invite_member_fields(data)
    if field_errors:
        return _validation_errors(field_errors)

    email = data["email"].strip().lower()
    role = data["role"].strip().lower()

    if role == Role.OWNER.value:
        return _validation_error("Cannot invite a user as owner")

    try:
        membership = invite_member(
            g.current_business,
            email=email,
            role=role,
            invited_by=g.current_user,
        )
        commit()
    except LookupError:
        return jsonify({"error": "User not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    return jsonify({"membership": membership.to_dict()}), 201


@businesses_bp.patch("/current/members/<int:membership_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_MEMBERS)
@db_session
def update_business_member(membership_id: int):
    data = _json_body()
    field_errors = validate_update_member_fields(data)
    if field_errors:
        return _validation_errors(field_errors)

    membership = get_membership_by_id(g.current_business, membership_id)
    if membership is None:
        return jsonify({"error": "Member not found"}), 404

    new_role = data.get("role")
    if (
        membership.user == g.current_user
        and new_role
        and new_role != membership.role.key
    ):
        return jsonify({"error": "You cannot change your own role"}), 403

    if new_role == Role.OWNER.value and not user_has_permission(PermissionKey.MANAGE_ROLES):
        return permission_denied(permission=PermissionKey.MANAGE_ROLES.value)

    try:
        update_member_role(
            membership,
            role=new_role,
            status=data.get("status"),
        )
        commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"membership": membership.to_dict()}), 200


@businesses_bp.delete("/current/members/<int:membership_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_MEMBERS)
@db_session
def remove_business_member(membership_id: int):
    membership = get_membership_by_id(g.current_business, membership_id)
    if membership is None:
        return jsonify({"error": "Member not found"}), 404

    if membership.user == g.current_user:
        return jsonify({"error": "You cannot remove yourself"}), 403

    if membership.role.key == Role.OWNER.value and not is_owner_membership(
        g.current_membership
    ):
        return permission_denied("Only owners can remove another owner")

    try:
        remove_member(membership)
        commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"message": "Member removed"}), 200


@businesses_bp.post("/current/members/accept")
@login_required
@db_session
def accept_current_business_invitation():
    if g.current_user.current_business_id is None:
        return jsonify({"error": "No business workspace selected"}), 400

    membership = get_membership(g.current_user, g.current_user.current_business_id)
    if membership is None or membership.status != MembershipStatus.INVITED.value:
        return jsonify({"error": "No pending invitation for the current business"}), 400

    from datetime import datetime

    membership.status = MembershipStatus.ACTIVE.value
    membership.joined_at = membership.joined_at or datetime.utcnow()
    membership.updated_at = datetime.utcnow()
    commit()
    return jsonify({"membership": membership.to_dict()}), 200
