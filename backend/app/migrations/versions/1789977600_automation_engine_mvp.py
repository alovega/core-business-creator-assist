"""Create automation definitions and automation run logs."""

from pony.orm import db_session

from app.automations.models import Automation, AutomationRun
from app.migrations.migration_helper import (
    create_table_from_model,
    drop_table,
    table_exists,
)


@db_session
def up(db):
    if not table_exists(db, Automation._table_):
        create_table_from_model(Automation)

    if not table_exists(db, AutomationRun._table_):
        create_table_from_model(AutomationRun)


@db_session
def down(db):
    if table_exists(db, AutomationRun._table_):
        drop_table(db, AutomationRun._table_)

    if table_exists(db, Automation._table_):
        drop_table(db, Automation._table_)