from flask import Blueprint

audit_logs_bp = Blueprint("audit_logs", __name__, url_prefix="/api/audit-logs")