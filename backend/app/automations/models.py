from datetime import datetime

from pony.orm import Json, Required

from app.db import db


class FAQEntry(db.Entity):
    _table_ = "faq_entries"

    business = Required("Business")
    question = Required(str)
    answer = Required(str)
    keywords_json = Required(Json, default=[])
    is_active = Required(bool, default=True)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "question": self.question,
            "answer": self.answer,
            "keywords": list(self.keywords_json or []),
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }


class AutoResponseRule(db.Entity):
    _table_ = "auto_response_rules"

    business = Required("Business")
    name = Required(str, max_len=255)
    trigger_type = Required(str, max_len=50)
    trigger_config_json = Required(Json, default={})
    response_text = Required(str)
    is_active = Required(bool, default=True)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "name": self.name,
            "trigger_type": self.trigger_type,
            "trigger_config": dict(self.trigger_config_json or {}),
            "response_text": self.response_text,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }
