"""Business workspace role keys (backed by app.common.rbac.models.Role)."""

from enum import StrEnum

from app.common.rbac.models import Role as RoleEntity


class RoleKey(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    STAFF = "staff"
    SUPPORT = "support"


# Backward-compatible alias used across the codebase.
Role = RoleKey

ALL_ROLES = frozenset(RoleKey)
ALL_ROLE_KEYS = ALL_ROLES

LEGACY_ROLE_ALIASES: dict[str, RoleKey] = {
    "user": RoleKey.STAFF,
}


def normalize_role(role: str | None) -> RoleKey | None:
    if role is None:
        return None
    try:
        return RoleKey(role)
    except ValueError:
        return LEGACY_ROLE_ALIASES.get(role)


def get_system_role(key: str) -> RoleEntity | None:
    normalized = key.lower()
    alias = LEGACY_ROLE_ALIASES.get(normalized)
    if alias is not None:
        normalized = alias.value
    return RoleEntity.get(key=normalized)
