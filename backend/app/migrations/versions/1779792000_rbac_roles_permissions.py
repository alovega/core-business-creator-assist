"""Add roles, permissions, role_permissions; link memberships to roles."""

from pony.orm import db_session

from app.businesses.models import BusinessMembership
from app.common.rbac.models import Permission, Role, RolePermission
from app.common.rbac.seed import ensure_rbac_seeded
from app.migrations.migration_helper import (
    add_column,
    add_column_from_model_property,
    add_fk_column,
    column_data_type,
    column_exists,
    create_table_from_model,
    drop_column,
    drop_table,
    rename_column,
    set_column_not_null,
    table_exists,
)

_MEMBERSHIPS_TABLE = BusinessMembership._table_
_ROLES_TABLE = Role._table_


def _membership_role_uses_fk(db) -> bool:
    if not column_exists(db, _MEMBERSHIPS_TABLE, "role"):
        return False
    data_type = column_data_type(db, _MEMBERSHIPS_TABLE, "role")
    return data_type in ("integer", "bigint", "smallint")


def _migrate_membership_role_text_to_fk(db) -> None:
    """Replace legacy text business_memberships.role with FK to roles."""
    if not table_exists(db, _MEMBERSHIPS_TABLE):
        return
    if _membership_role_uses_fk(db):
        return

    if column_exists(db, _MEMBERSHIPS_TABLE, "role_id"):
        if column_exists(db, _MEMBERSHIPS_TABLE, "role"):
            drop_column(db, _MEMBERSHIPS_TABLE, "role")
        rename_column(db, _MEMBERSHIPS_TABLE, "role_id", "role")
        set_column_not_null(db, _MEMBERSHIPS_TABLE, "role")
        return

    if not column_exists(db, _MEMBERSHIPS_TABLE, "role"):
        add_column_from_model_property(
            BusinessMembership.role,
            not_required_columns=["role"],
        )
        return

    add_fk_column(
        db,
        _MEMBERSHIPS_TABLE,
        "role_id",
        _ROLES_TABLE,
        on_delete="restrict",
        required=False,
    )
    db.execute(
        """
        UPDATE business_memberships AS bm
        SET role_id = r.id
        FROM roles AS r
        WHERE bm.role = r.key
        """
    )
    db.execute(
        """
        UPDATE business_memberships AS bm
        SET role_id = r.id
        FROM roles AS r
        WHERE bm.role_id IS NULL AND bm.role = 'user' AND r.key = 'staff'
        """
    )
    drop_column(db, _MEMBERSHIPS_TABLE, "role")
    rename_column(db, _MEMBERSHIPS_TABLE, "role_id", "role")
    set_column_not_null(db, _MEMBERSHIPS_TABLE, "role")


def _revert_membership_role_to_text(db) -> None:
    """Restore text business_memberships.role (pre-RBAC migration shape)."""
    if not table_exists(db, _MEMBERSHIPS_TABLE):
        return
    if not _membership_role_uses_fk(db):
        return

    add_column(db, _MEMBERSHIPS_TABLE, "role_legacy_text", "text", required=False)
    db.execute(
        """
        UPDATE business_memberships AS bm
        SET role_legacy_text = r.key
        FROM roles AS r
        WHERE bm.role = r.id
        """
    )
    drop_column(db, _MEMBERSHIPS_TABLE, "role")
    rename_column(db, _MEMBERSHIPS_TABLE, "role_legacy_text", "role")
    set_column_not_null(db, _MEMBERSHIPS_TABLE, "role")


@db_session
def up(db):
    if not table_exists(db, _ROLES_TABLE):
        create_table_from_model(Role)
    if not table_exists(db, Permission._table_):
        create_table_from_model(Permission)
    if not table_exists(db, RolePermission._table_):
        create_table_from_model(RolePermission)

    ensure_rbac_seeded()
    _migrate_membership_role_text_to_fk(db)


@db_session
def down(db):
    _revert_membership_role_to_text(db)

    drop_table(db, RolePermission._table_)
    drop_table(db, Permission._table_)
    drop_table(db, _ROLES_TABLE)
