"""Create payments table for manual payment tracking."""

from pony.orm import db_session

from app.migrations.migration_helper import create_table_from_model, drop_table, table_exists
from app.payments.models import Payment


@db_session
def up(db):
    if not table_exists(db, Payment._table_):
        create_table_from_model(Payment)


@db_session
def down(db):
    if table_exists(db, Payment._table_):
        drop_table(db, Payment._table_)