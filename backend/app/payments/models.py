from datetime import datetime
from decimal import Decimal

from pony.orm import Optional, Required, composite_index

from app.db import db

VALID_PAYMENT_STATUSES = frozenset({"pending", "paid", "failed", "cancelled"})
VALID_PAYMENT_METHODS = frozenset({"cash", "mpesa", "bank_transfer", "card", "other"})


class Payment(db.Entity):
    _table_ = "payments"

    business = Required("Business", reverse="payments")
    customer_id = Required(int)
    conversation = Optional("Conversation", reverse="payments")
    amount = Required(Decimal, precision=18, scale=2)
    currency = Required(str, max_len=3)
    reference = Optional(str, max_len=255, nullable=True)
    method = Required(str, max_len=50)
    status = Required(str, default="pending", max_len=50)
    notes = Optional(str, nullable=True)
    confirmed_by_user = Optional("User", reverse="confirmed_payments")
    confirmed_at = Optional(datetime, nullable=True)
    created_at = Required(datetime, default=datetime.utcnow)

    composite_index(business, customer_id)
    composite_index(business, status)
    composite_index(business, reference)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "customer_id": self.customer_id,
            "conversation_id": self.conversation.id if self.conversation else None,
            "amount": format(self.amount, "f"),
            "currency": self.currency,
            "reference": self.reference,
            "method": self.method,
            "status": self.status,
            "notes": self.notes,
            "confirmed_by_user_id": (
                self.confirmed_by_user.id if self.confirmed_by_user else None
            ),
            "confirmed_at": (
                self.confirmed_at.isoformat() + "Z" if self.confirmed_at else None
            ),
            "created_at": self.created_at.isoformat() + "Z",
        }