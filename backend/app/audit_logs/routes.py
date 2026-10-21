"""Read-only audit history with workspace and RBAC isolation."""
from flask import g, jsonify, request
from pony.orm import db_session, desc, select
from app.audit_logs import audit_logs_bp
from app.audit_logs.models import AuditLog
from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey

@audit_logs_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_AUDIT_LOGS)
@db_session
def list_audit_logs():
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "limit and offset must be integers"}), 400
    if not 1 <= limit <= 100 or offset < 0:
        return jsonify({"error": "limit must be 1-100 and offset nonnegative"}), 400
    business_id = g.current_business.id
    events = select(log for log in AuditLog if log.business_id == business_id)
    action = request.args.get("action")
    if action:
        events = events.filter(lambda log: log.action == action)
    total = events.count()
    rows = events.order_by(lambda log: (desc(log.created_at), desc(log.id)))[offset:offset + limit]
    return jsonify({"audit_logs": [row.to_dict() for row in rows], "total": total,
                    "limit": limit, "offset": offset}), 200