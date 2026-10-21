from datetime import datetime

from pony.orm import Optional, Required, composite_index

from app.db import db

VALID_BOOKING_STATUSES = frozenset(
    {"pending", "confirmed", "completed", "cancelled", "no_show"}
)


class Booking(db.Entity):
    _table_ = "bookings"

    business = Required("Business", reverse="bookings")
    customer_id = Required(int)
    conversation = Optional("Conversation", reverse="bookings")
    service_name = Required(str, max_len=255)
    scheduled_at = Required(datetime)
    duration_minutes = Required(int)
    status = Required(str, default="pending", max_len=50)
    notes = Optional(str, nullable=True)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)

    composite_index(business, scheduled_at)
    composite_index(business, customer_id)
    composite_index(business, status)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "customer_id": self.customer_id,
            "conversation_id": self.conversation.id if self.conversation else None,
            "service_name": self.service_name,
            "scheduled_at": self.scheduled_at.isoformat() + "Z",
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }