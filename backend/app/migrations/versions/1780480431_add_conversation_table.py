from pony.orm import db_session

from app.conversations.models import Conversation
from app.migrations.migration_helper import create_table_from_model, drop_table

@db_session
def up(db):
    create_table_from_model(Conversation)


@db_session
def down(db):
    drop_table(db, Conversation._table_)
