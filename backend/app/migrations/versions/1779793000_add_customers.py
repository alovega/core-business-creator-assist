"""Create customers table and enforce business+phone uniqueness."""

from pony.orm import db_session

from app.customers.models import Customer
from app.migrations.migration_helper import (
    add_composite_unique_constraint,
    add_missing_columns_from_model,
    create_table_from_model,
    table_exists,
)


@db_session
def up(db):
    if not table_exists(db, Customer._table_):
        create_table_from_model(Customer)
    else:
        add_missing_columns_from_model(Customer)

    add_composite_unique_constraint(
        db,
        Customer._table_,
        "business",
        "normalized_phone_number",
    )


@db_session
def down(db):
    from app.migrations.migration_helper import drop_table

    drop_table(db, Customer._table_)
