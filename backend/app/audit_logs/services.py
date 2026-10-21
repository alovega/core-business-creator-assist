"""Best-effort audit recording; accepts only explicitly approved metadata keys."""
import logging
from pony.orm import commit
from app.audit_logs.models import AuditLog

logger = logging.getLogger(__name__)
# Never accept arbitrary request bodies, message text, payment references or credentials.
SAFE_METADATA = frozenset({"from_stage", "to_stage", "from_status", "to_status", "operation", "channel", "message_type"})

def record_audit_event(*, business_id, user_id, action, resource_type, resource_id=None, metadata=None):
    if business_id is None:
        return False  # Do not create cross-tenant / unscoped records.
    safe_metadata = {key: value for key, value in (metadata or {}).items()
                     if key in SAFE_METADATA and (value is None or isinstance(value, (str, int, bool)))}
    try:
        AuditLog(business_id=int(business_id), user_id=int(user_id) if user_id is not None else None,
                 action=action, resource_type=resource_type, resource_id=resource_id,
                 metadata_json=safe_metadata)
        commit()
        return True
    except Exception:
        logger.exception("Audit event persistence failed (action=%s, business_id=%s)", action, business_id)
        return False