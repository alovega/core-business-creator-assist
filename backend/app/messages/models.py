from datetime import datetime

from pony.orm import Optional, Required, composite_index

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
    provider_media_id = Optional(str, max_len=255)
    storage_key = Optional(str, max_len=512)
    media_mime_type = Optional(str, max_len=150)
    media_filename = Optional(str, max_len=255)
    media_size_bytes = Optional(int)
    media_sha256 = Optional(str, max_len=64)
    media_status = Optional(str, max_len=30)
    provider_message_id = Optional(str, max_len=255)
    status = Required(str, default="pending", max_len=50)
    sent_by_user = Optional("User")
    created_at = Required(datetime, default=datetime.utcnow)

    composite_index(conversation, created_at)
    composite_index(business, created_at)
    composite_index(business, direction, created_at)

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
            "media_url": None if self.storage_key else self.media_url,
            "has_private_media": bool(self.storage_key),
            "media_mime_type": self.media_mime_type,
            "media_filename": self.media_filename,
            "media_size_bytes": self.media_size_bytes,
            "media_status": self.media_status,
            "media_download_path": f"/api/media/{self.id}" if self.storage_key else None,
            "provider_message_id": self.provider_message_id,
            "status": self.status,
            "sent_by_user_id": self.sent_by_user.id if self.sent_by_user else None,
            "created_at": self.created_at.isoformat() + "Z",
        }