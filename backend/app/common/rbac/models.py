"""Database-backed roles and permissions."""

from datetime import datetime

from pony.orm import Optional, PrimaryKey, Required, Set, composite_key

from app.db import db


class Role(db.Entity):
    _table_ = "roles"

    id = PrimaryKey(int, auto=True)
    key = Required(str, unique=True, max_len=50)
    name = Required(str, max_len=255)
    description = Optional(str)
    is_system = Required(bool, default=True)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)
    role_permissions = Set("RolePermission")
    memberships = Set("BusinessMembership")

    def __repr__(self) -> str:
        return f"<Role {self.key}>"


class Permission(db.Entity):
    _table_ = "permissions"

    id = PrimaryKey(int, auto=True)
    key = Required(str, unique=True, max_len=100)
    name = Required(str, max_len=255)
    description = Optional(str)
    category = Optional(str, max_len=100)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)
    role_permissions = Set("RolePermission")

    def __repr__(self) -> str:
        return f"<Permission {self.key}>"


class RolePermission(db.Entity):
    _table_ = "role_permissions"

    id = PrimaryKey(int, auto=True)
    role = Required(Role)
    permission = Required(Permission)
    created_at = Required(datetime, default=datetime.utcnow)

    composite_key(role, permission)

    def __repr__(self) -> str:
        return f"<RolePermission {self.role.key} -> {self.permission.key}>"
