"""Create bookings table."""

from pony.orm import db_session

from app.bookings.models import Booking
from app.migrations.migration_helper import (
    create_table_from_model,
    drop_table,
    table_exists,
)


@db_session
def up(db):
    if not table_exists(db, Booking._table_):
        create_table_from_model(Booking)


@db_session
def down(db):
    if table_exists(db, Booking._table_):
        drop_table(db, Booking._table_)