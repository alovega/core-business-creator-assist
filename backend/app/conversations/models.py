from datetime import datetime

from pony.orm import Json, Optional, Required, Set, composite_index, composite_key

from app.db import db


class Conversation(db.Entity):
    _table_ = "conversations"

    business = Required("Business")
    customer_id = Required(int)
    channel = Required(str, max_len=50)
    contact_phone_number = Optional(str, max_len=50)
    status = Required(str, default="open", max_len=50)
    assigned_to_user = Optional("User")
    assigned_to_membership = Optional("BusinessMembership")
    last_message_at = Optional(datetime)
    unread_count = Required(int, default=0)
    tags_json = Required(Json, default=[])
    priority = Required(str, default="normal", max_len=20)
    created_by = Optional("User")
    updated_by = Optional("User")
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)
    closed_at = Optional(datetime)
    messages = Set("Message")
    leads = Set("Lead")
    bookings = Set("Booking", reverse="conversation")
    payments = Set("Payment", reverse="conversation")

    composite_key(business, customer_id, channel)
    composite_index(business, updated_at)
    composite_index(business, last_message_at)
    composite_index(business, unread_count)
    composite_index(business, status)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "customer_id": self.customer_id,
            "channel": self.channel,
            "status": self.status,
            "assigned_to_user_id": self.assigned_to_user.id if self.assigned_to_user else None,
            "assigned_to_membership_id": (
                self.assigned_to_membership.id if self.assigned_to_membership else None
            ),
            "last_message_at": (
                self.last_message_at.isoformat() + "Z"
                if self.last_message_at
                else None
            ),
            "unread_count": self.unread_count,
            "tags": list(self.tags_json or []),
            "priority": self.priority,
            "created_by_id": self.created_by.id if self.created_by else None,
            "updated_by_id": self.updated_by.id if self.updated_by else None,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
            "closed_at": self.closed_at.isoformat() + "Z" if self.closed_at else None,
        }