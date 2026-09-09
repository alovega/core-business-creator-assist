from datetime import datetime

from pony.orm import Optional, Required

from app.db import db


class Lead(db.Entity):
    _table_ = "leads"

    business = Required("Business")
    conversation = Required("Conversation")
    customer_id = Optional(int)
    stage = Required(str, default="new", max_len=50)
    value = Optional(float, default=0.0)
    source = Optional(str, max_len=255)
    notes = Optional(str)
    assigned_to_user = Optional("User")
    next_follow_up_at = Optional(datetime)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "conversation_id": self.conversation.id,
            "customer_id": self.customer_id,
            "stage": self.stage,
            "value": self.value,
            "source": self.source,
            "notes": self.notes,
            "assigned_to_user_id": self.assigned_to_user.id if self.assigned_to_user else None,
            "next_follow_up_at": self.next_follow_up_at.isoformat() + "Z"
            if self.next_follow_up_at
            else None,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }
