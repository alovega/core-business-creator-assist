from datetime import datetime

from pony.orm import Optional, PrimaryKey, Required, composite_key

from app.common.time import utc_now_naive
from app.db import db


class WhatsAppIntegration(db.Entity):
    _table_ = "whatsapp_integrations"

    id = PrimaryKey(int, auto=True)
    business = Required("Business")
    phone_number_id = Required(str, max_len=255)
    whatsapp_business_account_id = Optional(str, max_len=255)
    display_phone_number = Optional(str, max_len=50)
    access_token_encrypted = Required(str)
    verify_token = Required(str, max_len=255)
    app_secret = Required(str)
    status = Required(str, default="connected", max_len=50)
    connected_at = Optional(datetime)
    disconnected_at = Optional(datetime)
    created_by = Optional("User", reverse="created_whatsapp_integrations")
    updated_by = Optional("User", reverse="updated_whatsapp_integrations")
    created_at = Required(datetime, default=utc_now_naive)
    updated_at = Required(datetime, default=utc_now_naive)

    composite_key(business, phone_number_id)
