"""Add indexes used by business-scoped dashboard metric queries."""

from pony.orm import db_session

from app.migrations.migration_helper import add_composite_index, table_exists


INDEXES = (
    ("conversations", ("business", "unread_count")),
    ("conversations", ("business", "status")),
    ("leads", ("business", "created_at")),
    ("leads", ("business", "stage")),
    ("messages", ("business", "created_at")),
    ("messages", ("business", "direction", "created_at")),
    ("payments", ("business", "created_at")),
)


@db_session
def up(db):
    for table_name, columns in INDEXES:
        if table_exists(db, table_name):
            add_composite_index(db, table_name, *columns)


@db_session
def down(db):
    for table_name, columns in INDEXES:
        suffix = "_".join(columns)
        db.execute(f'DROP INDEX IF EXISTS "idx_{table_name}__{suffix}"')