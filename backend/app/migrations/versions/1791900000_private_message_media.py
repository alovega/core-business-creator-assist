"""Add private media metadata to messages."""
from pony.orm import db_session
from app.migrations.migration_helper import add_column, column_exists, table_exists

COLUMNS = {'provider_media_id': 'text', 'storage_key': 'text', 'media_mime_type': 'text',
           'media_filename': 'text', 'media_size_bytes': 'int', 'media_sha256': 'text',
           'media_status': 'text'}

@db_session
def up(db):
    if not table_exists(db, 'messages'):
        return
    for name, kind in COLUMNS.items():
        if not column_exists(db, 'messages', name):
            add_column(db, 'messages', name, kind)

@db_session
def down(db):
    for name in reversed(list(COLUMNS)):
        if column_exists(db, 'messages', name):
            db.execute(f'ALTER TABLE "messages" DROP COLUMN "{name}"')