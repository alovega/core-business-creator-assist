"""Create persistent staff notifications table."""

from pony.orm import db_session

from app.migrations.migration_helper import create_table_from_model, drop_table, table_exists
from app.notifications.models import Notification


@db_session
def up(db):
    if not table_exists(db, Notification._table_):
        create_table_from_model(Notification)


@db_session
def down(db):
    if table_exists(db, Notification._table_):
        drop_table(db, Notification._table_)