"""Seed system roles and permissions."""

from __future__ import annotations

from datetime import datetime

from pony.orm import commit, db_session

from app.common.rbac.models import Permission, Role, RolePermission
from app.common.rbac.permissions import clear_permission_cache

SYSTEM_ROLES: tuple[dict, ...] = (
    {
        "key": "owner",
        "name": "Owner",
        "description": "Full control of the business workspace.",
    },
    {
        "key": "admin",
        "name": "Admin",
        "description": "Operational administration without owner-only actions.",
    },
    {
        "key": "staff",
        "name": "Staff",
        "description": "Day-to-day operational work.",
    },
    {
        "key": "support",
        "name": "Support",
        "description": "Limited customer-support access.",
    },
)

SYSTEM_PERMISSIONS: tuple[dict, ...] = (
    {
        "key": "manage_business_settings",
        "name": "Manage business settings",
        "category": "settings",
    },
    {
        "key": "manage_members",
        "name": "Manage members",
        "category": "members",
    },
    {
        "key": "manage_roles",
        "name": "Manage roles",
        "category": "members",
    },
    {
        "key": "manage_conversations",
        "name": "Manage conversations",
        "category": "conversations",
    },
    {
        "key": "manage_customers",
        "name": "Manage customers",
        "category": "customers",
    },
    {
        "key": "manage_leads",
        "name": "Manage leads",
        "category": "leads",
    },
    {
        "key": "manage_bookings",
        "name": "Manage bookings",
        "category": "bookings",
    },
    {
        "key": "manage_payments",
        "name": "Manage payments",
        "category": "payments",
    },
    {
        "key": "manage_automations",
        "name": "Manage automations",
        "category": "automations",
    },
    {
        "key": "view_dashboard",
        "name": "View dashboard",
        "category": "dashboard",
    },
    {
        "key": "view_audit_logs",
        "name": "View audit logs",
        "category": "audit",
    },
)

ALL_PERMISSION_KEYS: frozenset[str] = frozenset(p["key"] for p in SYSTEM_PERMISSIONS)

ROLE_PERMISSION_KEYS: dict[str, frozenset[str]] = {
    "owner": ALL_PERMISSION_KEYS,
    "admin": frozenset(
        key
        for key in ALL_PERMISSION_KEYS
        if key != "manage_roles"
    ),
    "staff": frozenset(
        {
            "manage_conversations",
            "manage_customers",
            "manage_leads",
            "manage_bookings",
            "view_dashboard",
        }
    ),
    "support": frozenset(
        {
            "manage_conversations",
            "manage_customers",
            "view_dashboard",
        }
    ),
}


def get_system_role(key: str) -> Role | None:
    return Role.get(key=key)


@db_session
def ensure_rbac_seeded() -> None:
    """Idempotently create system roles, permissions, and role-permission links."""
    clear_permission_cache()
    now = datetime.utcnow()

    permission_by_key: dict[str, Permission] = {}
    for spec in SYSTEM_PERMISSIONS:
        permission = Permission.get(key=spec["key"])
        if permission is None:
            permission = Permission(
                key=spec["key"],
                name=spec["name"],
                category=spec.get("category") or "",
                created_at=now,
                updated_at=now,
            )
        else:
            permission.name = spec["name"]
            if spec.get("category"):
                permission.category = spec["category"]
            permission.updated_at = now
        permission_by_key[spec["key"]] = permission

    role_by_key: dict[str, Role] = {}
    for spec in SYSTEM_ROLES:
        role = Role.get(key=spec["key"])
        if role is None:
            role = Role(
                key=spec["key"],
                name=spec["name"],
                is_system=True,
                created_at=now,
                updated_at=now,
            )
        else:
            role.name = spec["name"]
            role.is_system = True
            role.updated_at = now
        role_by_key[spec["key"]] = role

    for role_key, permission_keys in ROLE_PERMISSION_KEYS.items():
        role = role_by_key[role_key]
        desired = set(permission_keys)
        existing = {
            rp.permission.key for rp in role.role_permissions
        }
        for key in desired - existing:
            RolePermission(
                role=role,
                permission=permission_by_key[key],
                created_at=now,
            )
        for rp in list(role.role_permissions):
            if rp.permission.key not in desired:
                rp.delete()

    commit()
