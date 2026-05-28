"""Ensure business_memberships uses serial id + UNIQUE(user, business) (Solaris option 1)."""

from pony.orm import db_session

from app.businesses.models import BusinessMembership
from app.migrations.migration_helper import (
    column_exists,
    ensure_membership_user_business_unique,
    rebuild_table_with_serial_id,
    table_exists,
)

_MEMBERSHIP_COLUMNS = [
    "user",
    "business",
    "role",
    "status",
    "invited_by",
    "invited_at",
    "joined_at",
    "created_at",
    "updated_at",
]


@db_session
def up(db):
    table = BusinessMembership._table_
    if not table_exists(db, table):
        return

    if not column_exists(db, table, "id"):
        rebuild_table_with_serial_id(
            db,
            table,
            column_names=_MEMBERSHIP_COLUMNS,
        )

    ensure_membership_user_business_unique(db, table)


@db_session
def down(db):
    from app.migrations.migration_helper import remove_composite_unique_constraint

    if table_exists(db, BusinessMembership._table_):
        remove_composite_unique_constraint(
            db,
            BusinessMembership._table_,
            "user",
            "business",
        )
