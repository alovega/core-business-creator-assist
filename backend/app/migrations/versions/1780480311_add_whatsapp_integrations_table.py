from pony.orm import db_session

from app.whatsapp.models import WhatsAppIntegration
from app.migrations.migration_helper import create_table_from_model, drop_table

@db_session
def up(db):
    create_table_from_model(WhatsAppIntegration)


@db_session
def down(db):
    drop_table(db, WhatsAppIntegration._table_)
