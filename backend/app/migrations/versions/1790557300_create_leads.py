"""Create leads table."""

from pony.orm import db_session

from app.leads.models import Lead
from app.migrations.migration_helper import (
    create_table_from_model,
    drop_table,
    table_exists,
)


@db_session
def up(db):
    if not table_exists(db, Lead._table_):
        create_table_from_model(Lead)


@db_session
def down(db):
    if table_exists(db, Lead._table_):
        drop_table(db, Lead._table_)