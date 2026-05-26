"""Unit tests for database-backed role and permission resolution."""

from pony.orm import db_session

from app.common.rbac.permissions import PermissionKey, membership_has_permission
from app.common.rbac.roles import get_system_role
from app.common.rbac.seed import ROLE_PERMISSION_KEYS


def test_seeded_role_permission_map(app):

    @db_session
    def _check():
        owner = get_system_role("owner")
        admin = get_system_role("admin")
        staff = get_system_role("staff")
        support = get_system_role("support")

        assert owner is not None
        assert admin is not None
        assert staff is not None
        assert support is not None

        owner_keys = {rp.permission.key for rp in owner.role_permissions}
        assert owner_keys == set(ROLE_PERMISSION_KEYS["owner"])

        admin_keys = {rp.permission.key for rp in admin.role_permissions}
        assert PermissionKey.MANAGE_ROLES.value not in admin_keys
        assert PermissionKey.MANAGE_MEMBERS.value in admin_keys

        staff_keys = {rp.permission.key for rp in staff.role_permissions}
        assert PermissionKey.MANAGE_CONVERSATIONS.value in staff_keys
        assert PermissionKey.MANAGE_MEMBERS.value not in staff_keys

        support_keys = {rp.permission.key for rp in support.role_permissions}
        assert PermissionKey.MANAGE_CONVERSATIONS.value in support_keys
        assert PermissionKey.VIEW_DASHBOARD.value in support_keys
        assert PermissionKey.MANAGE_PAYMENTS.value not in support_keys

    _check()


def test_membership_resolves_permissions_through_role(client):
    from app.testing.helpers import create_business, register_user

    response = register_user(client, email="resolver@example.com")
    token = response.get_json()["access_token"]
    create_business(client, token)

    from app.businesses.models import BusinessMembership
    from app.users.models import User

    @db_session
    def _check():
        membership = BusinessMembership.get(
            user=User.get(email="resolver@example.com"),
            business=User.get(email="resolver@example.com").current_business,
        )
        assert membership is not None
        assert membership.role.key == "owner"
        assert membership_has_permission(membership, PermissionKey.MANAGE_MEMBERS)
        assert membership_has_permission(membership, PermissionKey.MANAGE_ROLES)

    _check()
