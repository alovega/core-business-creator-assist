"""Create FAQ entries and auto-response rules."""

from pony.orm import db_session

from app.automations.models import AutoResponseRule, FAQEntry
from app.migrations.migration_helper import create_table_from_model, drop_table, table_exists


@db_session
def up(db):
    if not table_exists(db, FAQEntry._table_):
        create_table_from_model(FAQEntry)
    if not table_exists(db, AutoResponseRule._table_):
        create_table_from_model(AutoResponseRule)


@db_session
def down(db):
    if table_exists(db, AutoResponseRule._table_):
        drop_table(db, AutoResponseRule._table_)
    if table_exists(db, FAQEntry._table_):
        drop_table(db, FAQEntry._table_)
