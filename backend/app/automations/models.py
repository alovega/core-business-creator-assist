from datetime import datetime

from pony.orm import Json, Required, composite_index, Optional, Set

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


class Automation(db.Entity):
    _table_ = "automations"

    business = Required("Business", reverse="automations")
    name = Required(str, max_len=255)

    trigger_type = Required(str, max_len=50)
    trigger_config_json = Required(Json, default={})

    action_type = Required(str, max_len=50)
    action_config_json = Required(Json, default={})

    is_active = Required(bool, default=True)

    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)

    runs = Set("AutomationRun", reverse="automation")

    composite_index(business, trigger_type, is_active)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "name": self.name,
            "trigger_type": self.trigger_type,
            "trigger_config": dict(self.trigger_config_json or {}),
            "action_type": self.action_type,
            "action_config": dict(self.action_config_json or {}),
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }


class AutomationRun(db.Entity):
    _table_ = "automation_runs"

    business = Required("Business", reverse="automation_runs")
    automation = Required(Automation, reverse="runs")

    trigger_type = Required(str, max_len=50)
    event_payload_json = Required(Json, default={})

    status = Required(str, default="pending", max_len=20)
    result_json = Required(Json, default={})
    error_message = Optional(str)

    started_at = Required(datetime, default=datetime.utcnow)
    completed_at = Optional(datetime)

    composite_index(business, started_at)
    composite_index(automation, started_at)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business.id,
            "automation_id": self.automation.id,
            "trigger_type": self.trigger_type,
            "event_payload": dict(self.event_payload_json or {}),
            "status": self.status,
            "result": dict(self.result_json or {}),
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() + "Z",
            "completed_at": (
                self.completed_at.isoformat() + "Z"
                if self.completed_at
                else None
            ),
        }