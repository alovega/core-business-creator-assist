"""Index timestamp scans used by inbox polling endpoints."""

from pony.orm import db_session

from app.migrations.migration_helper import add_composite_index, table_exists


@db_session
def up(db):
    if table_exists(db, "conversations"):
        add_composite_index(db, "conversations", "business", "updated_at")
    if table_exists(db, "messages"):
        add_composite_index(db, "messages", "conversation", "created_at")


@db_session
def down(db):
    db.execute(
        'DROP INDEX IF EXISTS "idx_conversations__business_updated_at"'
    )
    db.execute('DROP INDEX IF EXISTS "idx_messages__conversation_created_at"')