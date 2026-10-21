"""Business-scoped append-only audit events."""
from datetime import datetime
from pony.orm import Json, Optional, Required, composite_index
from app.db import db

class AuditLog(db.Entity):
    _table_ = "audit_logs"
    business_id = Required(int)
    user_id = Optional(int)
    action = Required(str, max_len=64)
    resource_type = Required(str, max_len=64)
    resource_id = Optional(int)
    metadata_json = Required(Json, default={})
    created_at = Required(datetime, default=datetime.utcnow)

    composite_index(business_id, created_at)
    composite_index(business_id, resource_type, resource_id)

    def to_dict(self):
        return {
            "id": self.id, "business_id": self.business_id, "user_id": self.user_id,
            "action": self.action, "resource_type": self.resource_type,
            "resource_id": self.resource_id, "metadata_json": dict(self.metadata_json or {}),
            "created_at": self.created_at.isoformat() + "Z",
        }