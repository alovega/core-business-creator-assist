"""Authentication, tenancy, role, and permission decorators."""

from functools import wraps

import jwt
from flask import current_app, g, jsonify, request
from pony.orm import db_session

from app.auth.services import decode_access_token, is_token_blacklisted
from app.businesses.models import Business, BusinessMembership
from app.common.rbac.access import (
    ErrorCode,
    auth_required,
    business_required_error,
    membership_required,
    permission_denied,
    role_required_error,
)
from app.common.rbac.permissions import (
    PermissionKey,
    membership_has_permission,
    membership_has_role,
)
from app.common.rbac.roles import ALL_ROLES, get_system_role
from app.common.tenant import resolve_current_business
from app.users.models import User


def get_current_business() -> Business | None:
    return getattr(g, "current_business", None)


def get_current_membership() -> BusinessMembership | None:
    return getattr(g, "current_membership", None)


def user_has_permission(permission: PermissionKey | str) -> bool:
    """Check permission for the current request membership."""
    membership = get_current_membership()
    return membership_has_permission(membership, permission)


def user_has_role(*role_keys: str) -> bool:
    membership = get_current_membership()
    return membership_has_role(membership, *role_keys)


def login_required(view):
    """Require a valid, non-revoked JWT and set g.current_user."""

    @wraps(view)
    @db_session
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return auth_required()

        token = auth_header[len("Bearer ") :]
        try:
            payload = decode_access_token(token, current_app.config["JWT_SECRET"])
        except jwt.ExpiredSignatureError:
            return auth_required("Token expired")
        except jwt.InvalidTokenError:
            return auth_required("Invalid token")

        if payload.get("type") != "access":
            return auth_required("Invalid token")

        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            return auth_required("Token revoked")

        user = User.get(id=int(payload.get("sub")))
        if user is None:
            return auth_required("User not found")
        if not user.is_active:
            return jsonify(
                {"error": ErrorCode.AUTH_REQUIRED, "message": "Account inactive"}
            ), 403

        g.current_user = user
        g.token_payload = payload
        return view(*args, **kwargs)

    return wrapped


def business_required(view):
    """Require an active membership for the current or requested business workspace."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        token_payload = getattr(g, "token_payload", None)
        business, membership = resolve_current_business(
            g.current_user,
            token_payload=token_payload,
            url_business_id=kwargs.get("business_id"),
        )
        if business is None:
            if kwargs.get("business_id") is not None:
                return membership_required(
                    "Access denied to this business workspace"
                )
            return business_required_error()

        if membership is None:
            if kwargs.get("business_id") is not None:
                return membership_required(
                    "Access denied to this business workspace"
                )
            return membership_required()

        g.business_id = business.id
        g.current_business = business
        g.current_membership = membership
        return view(*args, **kwargs)

    return wrapped


def role_required(*role_keys: str):
    """Require the current membership to have one of the given role keys."""

    allowed = frozenset(key.lower() for key in role_keys)

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            membership = get_current_membership()
            if membership is None or membership.role.key not in allowed:
                names = ", ".join(sorted(allowed))
                return role_required_error(
                    f"This action requires one of these roles: {names}"
                )
            return view(*args, **kwargs)

        return wrapped

    return decorator


def permission_required(permission: PermissionKey | str):
    """Require the current membership role to include the given permission."""

    perm_key = (
        permission.value if isinstance(permission, PermissionKey) else permission
    )

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            membership = get_current_membership()
            if not membership_has_permission(membership, perm_key):
                return permission_denied(permission=perm_key)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def assign_membership_role(
    membership: BusinessMembership,
    role_key: str,
) -> None:
    """Set a validated system role on a membership."""
    normalized = role_key.lower()
    if normalized not in ALL_ROLES:
        raise ValueError(f"Invalid role: {role_key}")
    role = get_system_role(normalized)
    if role is None:
        raise ValueError(f"System role not found: {role_key}")
    membership.role = role
