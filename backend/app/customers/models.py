from datetime import datetime
 
from pony.orm import Json, Optional, Required, composite_index, composite_key

from app.db import db


VALID_CUSTOMER_SOURCES = frozenset({"manual", "whatsapp", "import", "other"})
VALID_CUSTOMER_STATUSES = frozenset({"active", "inactive", "blocked"})


class Customer(db.Entity):
    _table_ = "customers"

    business = Required("Business", reverse="customers")
    name = Optional(str, max_len=255, nullable=True)
    phone_number = Required(str, max_len=50)
    normalized_phone_number = Required(str, max_len=50)
    email = Optional(str, max_len=255, nullable=True)
    source = Required(str, default="manual", max_len=50)
    tags_json = Required(Json, default=[])
    notes = Optional(str, nullable=True)
    status = Required(str, default="active", max_len=50)
    created_by = Optional("User", reverse="customers_created")
    updated_by = Optional("User", reverse="customers_updated")
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)

    composite_key(business, normalized_phone_number)
    composite_index(business, name)
    composite_index(business, email)
    composite_index(business, source)
    composite_index(business, status)