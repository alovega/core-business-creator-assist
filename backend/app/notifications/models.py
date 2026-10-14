from datetime import datetime

from pony.orm import Optional, Required, composite_index

from app.db import db


class Notification(db.Entity):
    _table_ = "notifications"

    business = Required("Business", reverse="notifications")
    user = Required("User", reverse="notifications")
    title = Required(str, max_len=255)
    message = Required(str)
    type = Required(str, max_len=50)
    is_read = Required(bool, default=False)
    link_url = Optional(str, max_len=2000, nullable=True)
    created_at = Required(datetime, default=datetime.utcnow)

    composite_index(business, user, created_at)
    composite_index(business, user, is_read)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "user_id": self.user.id,
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "is_read": self.is_read,
            "link_url": self.link_url,
            "created_at": self.created_at.isoformat() + "Z",
        }