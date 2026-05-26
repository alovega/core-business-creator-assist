"""Current business workspace resolution for multi-tenant requests."""

from __future__ import annotations

from flask import g, request, session

from app.businesses.membership_status import MembershipStatus
from app.businesses.models import Business, BusinessMembership
from app.users.models import User

BUSINESS_ID_HEADER = "X-Business-Id"
SESSION_BUSINESS_ID_KEY = "current_business_id"

ACTIVE_STATUS = MembershipStatus.ACTIVE.value


def active_memberships(user: User) -> list[BusinessMembership]:
    return [m for m in user.memberships if m.status == ACTIVE_STATUS]


def explicit_business_id_from_request() -> int | None:
    """Read an explicit workspace selection from the X-Business-Id header."""
    raw = request.headers.get(BUSINESS_ID_HEADER)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def business_id_from_session() -> int | None:
    raw = session.get(SESSION_BUSINESS_ID_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def business_id_from_token(token_payload: dict | None) -> int | None:
    if not token_payload:
        return None
    raw = token_payload.get("business_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def set_session_business_id(business_id: int | None) -> None:
    if business_id is None:
        session.pop(SESSION_BUSINESS_ID_KEY, None)
        return
    session[SESSION_BUSINESS_ID_KEY] = business_id


def persist_current_business(user: User, business: Business | None) -> None:
    user.current_business = business
    set_session_business_id(business.id if business is not None else None)


def ensure_default_current_business(user: User) -> int | None:
    """Default workspace when the user has exactly one active membership."""
    if user.current_business_id is not None:
        if user.active_membership_for_current_business() is not None:
            set_session_business_id(user.current_business_id)
            return user.current_business_id
        persist_current_business(user, None)

    memberships = active_memberships(user)
    if len(memberships) == 1:
        persist_current_business(user, memberships[0].business)
        return user.current_business_id
    return user.current_business_id


def resolve_current_business(
    user: User,
    *,
    token_payload: dict | None = None,
    url_business_id: int | None = None,
) -> tuple[Business | None, BusinessMembership | None]:
    """
    Resolve the workspace for this request.

    When url_business_id is set (e.g. GET /businesses/<id>), only that workspace
    is considered — no fallback to JWT/session/current.

    Otherwise order:
    1. X-Business-Id header (explicit selection)
    2. Flask session current_business_id
    3. JWT business_id claim
    4. user.current_business when membership is active
    5. Single active membership fallback
    """
    if url_business_id is not None:
        membership = user.active_membership_for(url_business_id)
        if membership is not None:
            return membership.business, membership
        return None, None

    candidates: list[int | None] = [
        explicit_business_id_from_request(),
        business_id_from_session(),
        business_id_from_token(token_payload),
        user.current_business_id,
    ]

    seen: set[int] = set()
    for business_id in candidates:
        if business_id is None or business_id in seen:
            continue
        seen.add(business_id)
        membership = user.active_membership_for(business_id)
        if membership is not None:
            return membership.business, membership

    memberships = active_memberships(user)
    if len(memberships) == 1:
        membership = memberships[0]
        persist_current_business(user, membership.business)
        return membership.business, membership

    return None, None


def current_business_id() -> int | None:
    return getattr(g, "business_id", None)


def require_business(view):
    from app.common.rbac.decorators import business_required

    return business_required(view)


__all__ = [
    "BUSINESS_ID_HEADER",
    "SESSION_BUSINESS_ID_KEY",
    "active_memberships",
    "business_id_from_session",
    "business_id_from_token",
    "current_business_id",
    "ensure_default_current_business",
    "explicit_business_id_from_request",
    "persist_current_business",
    "require_business",
    "resolve_current_business",
    "set_session_business_id",
]
