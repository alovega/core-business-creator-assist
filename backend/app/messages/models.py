from datetime import datetime

from pony.orm import Json, Optional, PrimaryKey, Required, composite_key

from app.common.time import utc_now_naive
from app.db import db


class Message(db.Entity):
    _table_ = "messages"

    id = PrimaryKey(int, auto=True)
    business = Required("Business")
    conversation = Required("Conversation")
    customer = Required("Customer")
    channel = Required(str, default="whatsapp", max_len=50)
    direction = Required(str, default="inbound", max_len=20)
    status = Required(str, default="received", max_len=50)
    body = Optional(str)
    provider_message_id = Optional(str, max_len=255)
    provider_payload = Required(Json, default={})
    delivered_at = Optional(datetime)
    failed_at = Optional(datetime)
    failure_reason = Optional(str)
    created_at = Required(datetime, default=utc_now_naive)
    updated_at = Required(datetime, default=utc_now_naive)

    composite_key(business, provider_message_id)
