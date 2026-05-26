"""Tests for model-driven migration helpers."""

from app.businesses.models import Business
from app.migrations.migration_helper import (
    PY_TYPES_TO_SQL,
    discover_entity_classes,
    get_default_from_property,
)
from app.users.models import User


def test_discover_entity_classes(app):
    from app.common.rbac.models import Permission, Role, RolePermission
    from app.businesses.models import BusinessMembership

    registry = discover_entity_classes()
    assert "User" in registry
    assert "Business" in registry
    assert "BusinessMembership" in registry
    assert "Role" in registry
    assert "Permission" in registry
    assert "RolePermission" in registry
    assert registry["User"] is User
    assert registry["Role"] is Role
    assert registry["BusinessMembership"] is BusinessMembership


def test_entity_attrs_map_to_sql_types():
    for prop in User._attrs_:
        if not prop.column or prop.is_relation:
            continue
        assert prop.py_type in PY_TYPES_TO_SQL


def test_get_default_from_property_handles_literals():
    assert get_default_from_property(True) is True
    assert get_default_from_property("active") == "active"
