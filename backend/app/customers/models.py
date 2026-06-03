from datetime import datetime

from pony.orm import Json, Optional, PrimaryKey, Required, Set, composite_key

from app.common.time import utc_now_naive
from app.db import db


class Customer(db.Entity):
    _table_ = "customers"

    id = PrimaryKey(int, auto=True)
    business = Required("Business")
    name = Required(str, max_len=255)
    phone_number = Required(str, max_len=50)
    normalized_phone_number = Required(str, max_len=50)
    email = Optional(str, max_len=255)
    source = Required(str, default="manual", max_len=50)
    tags_json = Required(Json, default=[])
    notes = Optional(str)
    status = Required(str, default="active", max_len=50)
    created_by = Optional("User", reverse="created_customers")
    updated_by = Optional("User", reverse="updated_customers")
    conversations = Set("Conversation")
    messages = Set("Message")
    created_at = Required(datetime, default=utc_now_naive)
    updated_at = Required(datetime, default=utc_now_naive)

    composite_key(business, normalized_phone_number)
