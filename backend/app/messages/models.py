from datetime import datetime

from pony.orm import Optional, Required

from app.db import db


class Message(db.Entity):
    _table_ = "messages"

    business = Required("Business")
    conversation = Required("Conversation")
    customer_id = Optional(int)
    direction = Required(str, max_len=20)
    channel = Required(str, max_len=50)
    message_type = Required(str, max_len=50)
    body = Optional(str)
    media_url = Optional(str, max_len=2000)
    provider_message_id = Optional(str, max_len=255)
    status = Required(str, default="pending", max_len=50)
    sent_by_user = Optional("User")
    created_at = Required(datetime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "conversation_id": self.conversation.id,
            "customer_id": self.customer_id,
            "direction": self.direction,
            "channel": self.channel,
            "message_type": self.message_type,
            "body": self.body,
            "media_url": self.media_url,
            "provider_message_id": self.provider_message_id,
            "status": self.status,
            "sent_by_user_id": self.sent_by_user.id if self.sent_by_user else None,
            "created_at": self.created_at.isoformat() + "Z",
        }