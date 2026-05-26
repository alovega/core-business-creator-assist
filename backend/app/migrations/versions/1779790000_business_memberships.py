"""Migrate users.business + users.role to business_memberships."""

from datetime import datetime

from pony.orm import db_session

from app.businesses.models import BusinessMembership
from app.migrations.migration_helper import (
    add_column,
    add_column_from_model_property,
    add_missing_columns_from_model,
    column_data_type,
    column_exists,
    create_table_from_model,
    drop_column,
    ensure_membership_user_business_unique,
    table_exists,
)
from app.users.models import User

_MEMBERSHIPS_TABLE = BusinessMembership._table_


def _ensure_memberships_text_role_column(db) -> None:
    """role is VARCHAR until 1779792000_rbac_roles_permissions creates roles FK."""
    if not column_exists(db, _MEMBERSHIPS_TABLE, "role"):
        add_column(db, _MEMBERSHIPS_TABLE, "role", "text", required=True, default="owner")
        return

    role_type = column_data_type(db, _MEMBERSHIPS_TABLE, "role")
    if role_type in ("integer", "bigint", "smallint") and not table_exists(db, "roles"):
        drop_column(db, _MEMBERSHIPS_TABLE, "role")
        add_column(db, _MEMBERSHIPS_TABLE, "role", "text", required=True, default="owner")


@db_session
def up(db):
    if not table_exists(db, _MEMBERSHIPS_TABLE):
        create_table_from_model(
            BusinessMembership,
            skip_columns=["role"],
            unique_composite=[("user", "business")],
        )
        _ensure_memberships_text_role_column(db)
    else:
        add_missing_columns_from_model(BusinessMembership, skip_columns=["role"])
        _ensure_memberships_text_role_column(db)

    if column_exists(db, "users", "business"):
        rows = db.select(
            'SELECT id, business, role FROM "users" WHERE business IS NOT NULL'
        )
        now = datetime.utcnow().isoformat(sep=" ")
        for row in rows:
            user_id, business_id, role = row
            role_value = role or "owner"
            existing = db.select(
                "SELECT 1 FROM business_memberships "
                f'WHERE "user" = {user_id} AND business = {business_id} LIMIT 1'
            )
            if list(existing):
                continue
            db.execute(
                'INSERT INTO business_memberships '
                '("user", business, role, status, joined_at, created_at, updated_at) '
                f"VALUES ({user_id}, {business_id}, '{role_value}', 'active', "
                f"'{now}', '{now}', '{now}')"
            )

    if not column_exists(db, "users", "current_business"):
        add_column_from_model_property(User.current_business, not_required_columns=["current_business"])

    if column_exists(db, "users", "business"):
        db.execute(
            'UPDATE "users" SET current_business = business WHERE business IS NOT NULL'
        )
        drop_column(db, "users", "business")

    if column_exists(db, "users", "role"):
        drop_column(db, "users", "role")

    ensure_membership_user_business_unique(db)


@db_session
def down(db):
    from app.migrations.migration_helper import drop_table

    if column_exists(db, "users", "current_business"):
        drop_column(db, "users", "current_business")

    if table_exists(db, "business_memberships"):
        drop_table(db, BusinessMembership._table_)
