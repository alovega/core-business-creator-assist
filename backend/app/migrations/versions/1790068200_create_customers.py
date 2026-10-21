"""Create customers table."""

from pony.orm import db_session

from app.customers.models import Customer
from app.migrations.migration_helper import (
    create_table_from_model,
    drop_table,
    table_exists,
)


@db_session
def up(db):
    if not table_exists(db, Customer._table_):
        create_table_from_model(Customer)


@db_session
def down(db):
    if table_exists(db, Customer._table_):
        drop_table(db, Customer._table_)