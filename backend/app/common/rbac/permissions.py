"""Permission keys and membership-based permission resolution."""

from __future__ import annotations

from enum import StrEnum

from app.businesses.models import BusinessMembership

# Keys in business settings_json that only the owner role may read or write.
OWNER_ONLY_SETTING_KEYS = frozenset(
    {
        "billing",
        "subscription",
        "api_keys",
        "webhooks",
        "owner_notifications",
    }
)

_permission_cache: dict[str, frozenset[str]] | None = None


class PermissionKey(StrEnum):
    MANAGE_BUSINESS_SETTINGS = "manage_business_settings"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_ROLES = "manage_roles"
    MANAGE_CONVERSATIONS = "manage_conversations"
    MANAGE_CUSTOMERS = "manage_customers"
    MANAGE_LEADS = "manage_leads"
    MANAGE_BOOKINGS = "manage_bookings"
    MANAGE_PAYMENTS = "manage_payments"
    MANAGE_AUTOMATIONS = "manage_automations"
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_AUDIT_LOGS = "view_audit_logs"


def clear_permission_cache() -> None:
    global _permission_cache
    _permission_cache = None


def _permission_keys_for_role(role_key: str) -> frozenset[str]:
    global _permission_cache
    if _permission_cache is None:
        from app.common.rbac.models import Role

        cache: dict[str, frozenset[str]] = {}
        for role in Role.select():
            cache[role.key] = frozenset(
                rp.permission.key for rp in role.role_permissions
            )
        _permission_cache = cache
    return _permission_cache.get(role_key, frozenset())


def membership_has_permission(
    membership: BusinessMembership | None,
    permission: PermissionKey | str,
) -> bool:
    if membership is None:
        return False
    perm_key = permission.value if isinstance(permission, PermissionKey) else permission
    role_key = membership.role.key
    return perm_key in _permission_keys_for_role(role_key)


def user_has_permission(
    membership: BusinessMembership | None,
    permission: PermissionKey | str,
) -> bool:
    """Check permission for an active business membership (not a global user role)."""
    return membership_has_permission(membership, permission)


def membership_has_role(
    membership: BusinessMembership | None,
    *role_keys: str,
) -> bool:
    if membership is None:
        return False
    allowed = {key.lower() for key in role_keys}
    return membership.role.key in allowed


def is_owner_membership(membership: BusinessMembership | None) -> bool:
    return membership_has_role(membership, "owner")
