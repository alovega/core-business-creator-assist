from pony.orm import db_session

from app.customers.models import Customer
from app.migrations.migration_helper import create_table_from_model, drop_table


@db_session
def up(db):
    create_table_from_model(Customer)


@db_session
def down(db):
    drop_table(db, Customer._table_)
