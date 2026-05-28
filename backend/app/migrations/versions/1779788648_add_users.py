from pony.orm import db_session

from app.businesses.models import Business
from app.migrations.migration_helper import create_table_from_model, drop_table
from app.users.models import User


@db_session
def up(db):
    create_table_from_model(Business)
    create_table_from_model(User)


@db_session
def down(db):
    drop_table(db, User._table_)
    drop_table(db, Business._table_)
