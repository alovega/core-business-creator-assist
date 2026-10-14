"""Create business-scoped audit_logs table."""
from pony.orm import db_session
from app.audit_logs.models import AuditLog
from app.migrations.migration_helper import create_table_from_model, drop_table, table_exists

@db_session
def up(db):
    if not table_exists(db, AuditLog._table_):
        create_table_from_model(AuditLog)

@db_session
def down(db):
    if table_exists(db, AuditLog._table_):
        drop_table(db, AuditLog._table_)