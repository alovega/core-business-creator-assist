"""Create conversations and persisted messages."""

from pony.orm import db_session

from app.conversations.models import Conversation
from app.messages.models import Message
from app.migrations.migration_helper import create_table_from_model, drop_table, table_exists


@db_session
def up(db):
    if not table_exists(db, Conversation._table_):
        create_table_from_model(Conversation)
    if not table_exists(db, Message._table_):
        create_table_from_model(Message)


@db_session
def down(db):
    if table_exists(db, Message._table_):
        drop_table(db, Message._table_)
    if table_exists(db, Conversation._table_):
        drop_table(db, Conversation._table_)
