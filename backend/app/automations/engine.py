from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pony.orm import commit, select

from app.automations.models import Automation, AutomationRun
from app.businesses.membership_status import MembershipStatus
from app.businesses.models import BusinessMembership
from app.common.logging import get_logger
from app.conversations.models import Conversation
import app.extensions as extensions
from app.leads.models import Lead, VALID_LEAD_STAGES
from app.messages.models import Message
from app.messages.services import send_whatsapp_message

logger = get_logger("app.automations")

SUPPORTED_TRIGGERS = frozenset(
    {
        "new_message_received",
        "customer_created",
        "lead_created",
        "booking_created",
        "payment_marked_paid",
    }
)

SUPPORTED_ACTIONS = frozenset(
    {
        "send_whatsapp_message",
        "create_lead",
        "update_lead_stage",
        "create_follow_up_reminder",
        "notify_staff",
    }
)


def _trigger_matches(automation: Automation, payload: dict[str, Any]) -> bool:
    config = dict(automation.trigger_config_json or {})
    return all(payload.get(key) == value for key, value in config.items())


def _configured_id(config: dict, payload: dict, key: str) -> int | None:
    value = config.get(key, payload.get(key))
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _conversation_for_business(business, config: dict, payload: dict) -> Conversation:
    conversation_id = _configured_id(config, payload, "conversation_id")
    if conversation_id is None:
        raise ValueError("conversation_id is required for this action")
    conversation = Conversation.get(id=conversation_id, business=business)
    if conversation is None:
        raise ValueError("conversation does not belong to this business")
    return conversation


def _lead_for_business(business, config: dict, payload: dict) -> Lead:
    lead_id = _configured_id(config, payload, "lead_id")
    if lead_id is None:
        raise ValueError("lead_id is required for this action")
    lead = Lead.get(id=lead_id, business=business)
    if lead is None:
        raise ValueError("lead does not belong to this business")
    return lead


def _render_text(template: str, payload: dict[str, Any]) -> str:
    class SafePayload(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return template.format_map(SafePayload(payload)).strip()


def _send_whatsapp_action(business, config: dict, payload: dict) -> dict:
    conversation = _conversation_for_business(business, config, payload)
    template = config.get("message", config.get("body"))
    if not isinstance(template, str) or not template.strip():
        raise ValueError("action_config.message is required")

    recipient = str(conversation.contact_phone_number or "").strip()
    if not recipient:
        raise ValueError("WhatsApp recipient is required")

    body = _render_text(template, payload)
    if not body:
        raise ValueError("rendered WhatsApp message is empty")

    message = Message(
        business=business,
        conversation=conversation,
        customer_id=conversation.customer_id,
        direction="outgoing",
        channel="whatsapp",
        message_type="text",
        body=body,
        status="pending",
    )
    conversation.last_message_at = message.created_at
    conversation.updated_at = datetime.utcnow()
    commit()

    try:
        message.provider_message_id = send_whatsapp_message(message, recipient)
        message.status = "sent"
        commit()
    except Exception:
        message.status = "failed"
        commit()
        raise

    return {"message_id": message.id, "provider_message_id": message.provider_message_id}


def _create_lead_action(business, config: dict, payload: dict) -> dict:
    conversation = _conversation_for_business(business, config, payload)
    stage = str(config.get("stage", "new")).strip().lower()
    if stage not in VALID_LEAD_STAGES:
        raise ValueError("action_config.stage is invalid")

    raw_value = config.get("value", 0.0)
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise ValueError("action_config.value must be a number")

    lead_data = {
        "business": business,
        "conversation": conversation,
        "customer_id": conversation.customer_id,
        "stage": stage,
        "value": float(raw_value),
    }
    source = config.get("source")
    notes = config.get("notes")
    if isinstance(source, str) and source.strip():
        lead_data["source"] = source.strip()
    if isinstance(notes, str) and notes.strip():
        lead_data["notes"] = _render_text(notes, payload)

    lead = Lead(**lead_data)
    commit()
    return {"lead_id": lead.id}


def _update_lead_stage_action(business, config: dict, payload: dict) -> dict:
    lead = _lead_for_business(business, config, payload)
    stage = config.get("stage")
    if not isinstance(stage, str) or stage.strip().lower() not in VALID_LEAD_STAGES:
        raise ValueError("action_config.stage is required and must be a valid lead stage")

    lead.stage = stage.strip().lower()
    lead.updated_at = datetime.utcnow()
    commit()
    return {"lead_id": lead.id, "stage": lead.stage}


def _parse_run_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("action_config.run_at must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _create_follow_up_reminder_action(business, config: dict, payload: dict) -> dict:
    lead = _lead_for_business(business, config, payload)
    run_at = config.get("run_at")
    if run_at is not None:
        if not isinstance(run_at, str) or not run_at.strip():
            raise ValueError("action_config.run_at must be an ISO-8601 datetime")
        next_follow_up_at = _parse_run_at(run_at.strip())
    else:
        delay_minutes = config.get("delay_minutes", 60)
        if (
            isinstance(delay_minutes, bool)
            or not isinstance(delay_minutes, int)
            or delay_minutes < 0
        ):
            raise ValueError("action_config.delay_minutes must be a non-negative integer")
        next_follow_up_at = datetime.utcnow() + timedelta(minutes=delay_minutes)

    lead.next_follow_up_at = next_follow_up_at
    lead.updated_at = datetime.utcnow()
    commit()
    return {"lead_id": lead.id, "next_follow_up_at": next_follow_up_at.isoformat() + "Z"}


def _notify_staff_action(business, config: dict, payload: dict) -> dict:
    template = config.get("message")
    if not isinstance(template, str) or not template.strip():
        raise ValueError("action_config.message is required")

    requested_user_ids = config.get("user_ids")
    if requested_user_ids is not None:
        if not isinstance(requested_user_ids, list):
            raise ValueError("action_config.user_ids must be a list")
        try:
            requested_user_ids = {int(user_id) for user_id in requested_user_ids}
        except (TypeError, ValueError) as exc:
            raise ValueError("action_config.user_ids must contain integers") from exc

    memberships = list(
        select(
            membership
            for membership in BusinessMembership
            if membership.business == business
            and membership.status == MembershipStatus.ACTIVE.value
        )
    )
    recipient_user_ids = [
        membership.user.id
        for membership in memberships
        if requested_user_ids is None or membership.user.id in requested_user_ids
    ]
    message = _render_text(template, payload)
    if not recipient_user_ids:
        raise ValueError("no active staff recipients were found for this business")

    notification = {
        "type": "automation_staff_notification",
        "business_id": business.id,
        "recipient_user_ids": recipient_user_ids,
        "message": message,
    }
    if extensions.redis_client is not None:
        extensions.redis_client.publish(
            f"business:{business.id}:notifications",
            json.dumps(notification),
        )

    logger.info("automation_staff_notification", **notification)
    return notification


ActionHandler = Callable[[Any, dict, dict], dict]

ACTION_HANDLERS: dict[str, ActionHandler] = {
    "send_whatsapp_message": _send_whatsapp_action,
    "create_lead": _create_lead_action,
    "update_lead_stage": _update_lead_stage_action,
    "create_follow_up_reminder": _create_follow_up_reminder_action,
    "notify_staff": _notify_staff_action,
}


def dispatch_automation_event(
    business,
    trigger_type: str,
    payload: dict[str, Any] | None = None,
) -> list[AutomationRun]:
    """Run active automations for a business event without bubbling action failures."""
    if trigger_type not in SUPPORTED_TRIGGERS:
        raise ValueError(f"Unsupported automation trigger: {trigger_type}")

    event_payload = dict(payload or {})
    automations = list(
        select(
            automation
            for automation in Automation
            if automation.business == business
            and automation.is_active
            and automation.trigger_type == trigger_type
        ).order_by(lambda automation: automation.id)
    )

    runs: list[AutomationRun] = []
    for automation in automations:
        if not _trigger_matches(automation, event_payload):
            continue

        run = AutomationRun(
            business=business,
            automation=automation,
            trigger_type=trigger_type,
            event_payload_json=event_payload,
            status="pending",
        )
        commit()
        runs.append(run)

        try:
            handler = ACTION_HANDLERS.get(automation.action_type)
            if handler is None:
                raise ValueError(f"Unsupported automation action: {automation.action_type}")
            result = handler(
                business,
                dict(automation.action_config_json or {}),
                event_payload,
            )
            run.status = "success"
            run.result_json = result or {}
            run.error_message = ""
        except Exception as exc:
            run.status = "failed"
            run.result_json = {}
            run.error_message = str(exc)[:4000]
            logger.exception(
                "automation_run_failed",
                automation_id=automation.id,
                business_id=business.id,
                trigger_type=trigger_type,
            )
        finally:
            run.completed_at = datetime.utcnow()
            commit()

    return runs


def dispatch_new_message_received(message: Message) -> list[AutomationRun]:
    if message.direction != "incoming":
        return []
    return dispatch_automation_event(
        message.business,
        "new_message_received",
        {
            "message_id": message.id,
            "conversation_id": message.conversation.id,
            "customer_id": message.customer_id,
            "channel": message.channel,
            "message_type": message.message_type,
            "body": message.body or "",
        },
    )