from datetime import datetime

from pony.orm import Optional, Required

from app.db import db


class Customer(db.Entity):
    _table_ = "customers"

    business = Required("Business", reverse="customers")
    external_id = Optional(str, max_len=255)
    name = Optional(str, max_len=255)
    email = Optional(str, max_len=255)
    phone_number = Optional(str, max_len=50)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)
