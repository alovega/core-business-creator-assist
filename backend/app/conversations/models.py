from datetime import datetime

from pony.orm import Optional, Required, Set, composite_index

from app.db import db


class Conversation(db.Entity):
    _table_ = "conversations"

    business = Required("Business")
    customer_id = Optional(int)
    channel = Required(str, max_len=50)
    contact_phone_number = Optional(str, max_len=50)
    last_message_at = Optional(datetime)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)
    messages = Set("Message")
    leads = Set("Lead")

    composite_index(business, customer_id)
    composite_index(business, updated_at)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "customer_id": self.customer_id,
            "channel": self.channel,
            "contact_phone_number": self.contact_phone_number,
            "last_message_at": (
                self.last_message_at.isoformat() + "Z"
                if self.last_message_at
                else None
            ),
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }