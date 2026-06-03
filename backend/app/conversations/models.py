from datetime import datetime

from pony.orm import Json, Optional, PrimaryKey, Required, Set, composite_key

from app.common.time import utc_now_naive
from app.db import db


class Conversation(db.Entity):
    _table_ = "conversations"

    id = PrimaryKey(int, auto=True)
    business = Required("Business")
    customer = Required("Customer")
    channel = Required(str, default="whatsapp", max_len=50)
    status = Required(str, default="open", max_len=50)
    assigned_to = Optional("BusinessMembership", reverse="assigned_conversations")
    assigned_user = Optional("User", reverse="assigned_conversations")
    last_message_at = Optional(datetime)
    unread_count = Required(int, default=0)
    tags_json = Required(Json, default=[])
    priority = Required(str, default="normal", max_len=50)
    created_by = Optional("User", reverse="created_conversations")
    updated_by = Optional("User", reverse="updated_conversations")
    created_at = Required(datetime, default=utc_now_naive)
    updated_at = Required(datetime, default=utc_now_naive)
    closed_at = Optional(datetime)
    messages = Set("Message")

    composite_key(business, customer, channel)
