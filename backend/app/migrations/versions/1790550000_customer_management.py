"""Complete customer management schema."""

from pony.orm import db_session

from app.customers.models import Customer
from app.migrations.migration_helper import (
    add_column,
    add_composite_index,
    add_composite_unique_constraint,
    add_fk_column,
    column_exists,
    remove_composite_unique_constraint,
    set_column_not_null,
    table_exists,
)

TABLE = Customer._table_


@db_session
def up(db):
    if not table_exists(db, TABLE):
        return

    if not column_exists(db, TABLE, "normalized_phone_number"):
        add_column(db, TABLE, "normalized_phone_number", "text", required=False)
    if not column_exists(db, TABLE, "source"):
        add_column(db, TABLE, "source", "text", required=True, default="manual")
    if not column_exists(db, TABLE, "tags_json"):
        db.execute(
            'ALTER TABLE "customers" ADD COLUMN "tags_json" JSONB '
            "NOT NULL DEFAULT CAST('[]' AS jsonb)"
        )
    if not column_exists(db, TABLE, "notes"):
        add_column(db, TABLE, "notes", "text", required=False)
    if not column_exists(db, TABLE, "status"):
        add_column(db, TABLE, "status", "text", required=True, default="active")
    if not column_exists(db, TABLE, "created_by"):
        add_fk_column(db, TABLE, "created_by", "users", required=False)
    if not column_exists(db, TABLE, "updated_by"):
        add_fk_column(db, TABLE, "updated_by", "users", required=False)

    # Existing records pre-date normalization. Preserve them while creating a
    # stable tenant-scoped key; new/updated records are normalized by services.
    db.execute("""
        UPDATE customers
        SET phone_number = COALESCE(NULLIF(TRIM(phone_number), ''), 'legacy-' || CAST(id AS text))
        WHERE phone_number IS NULL OR TRIM(phone_number) = ''
        """)
    db.execute("""
        UPDATE customers
        SET normalized_phone_number = CASE
            WHEN normalized_phone_number IS NOT NULL
                 AND TRIM(normalized_phone_number) <> ''
                THEN normalized_phone_number
            WHEN phone_number ~ '[0-9]'
     AND phone_number !~ '[^0-9+ ()\\.-]'
    THEN regexp_replace(
        phone_number,
        '[^0-9]',
        '',
        'g'
    )
            ELSE 'legacy-' || CAST(id AS text)
        END
        WHERE normalized_phone_number IS NULL OR TRIM(normalized_phone_number) = ''
        """)

    set_column_not_null(db, TABLE, "phone_number")
    set_column_not_null(db, TABLE, "normalized_phone_number")

    add_composite_unique_constraint(db, TABLE, "business", "normalized_phone_number")
    add_composite_index(db, TABLE, "business", "name")
    add_composite_index(db, TABLE, "business", "email")
    add_composite_index(db, TABLE, "business", "source")
    add_composite_index(db, TABLE, "business", "status")
