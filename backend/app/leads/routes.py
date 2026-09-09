from datetime import datetime

from flask import g, jsonify, request
from pony.orm import commit, db_session, select

from app.businesses.membership_status import MembershipStatus
from app.businesses.models import BusinessMembership
from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.conversations.models import Conversation
from app.leads import leads_bp
from app.leads.models import Lead
from app.users.models import User

VALID_LEAD_STAGES = frozenset({"new", "interested", "negotiating", "booked", "paid", "lost"})


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


def _conversation_for_current_business(conversation_id: int) -> Conversation | None:
    return Conversation.get(id=conversation_id, business=g.current_business)


def _lead_for_current_business(lead_id: int) -> Lead | None:
    return Lead.get(id=lead_id, business=g.current_business)


def _parse_optional_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("next_follow_up_at must be an ISO-8601 datetime string")
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("next_follow_up_at must be an ISO-8601 datetime string") from exc
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _coerce_optional_float(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a number")
    return float(value)


def _validate_stage(stage: str | None):
    if stage is None:
        return None
    normalized = str(stage).strip().lower()
    if normalized not in VALID_LEAD_STAGES:
        raise ValueError(
            "stage must be one of: new, interested, negotiating, booked, paid, lost"
        )
    return normalized


def _validate_assignee(user_id):
    if user_id is None:
        return None
    try:
        target_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("assigned_to_user_id must be an integer")

    user = User.get(id=target_id)
    if user is None:
        raise LookupError("assigned_to_user_id must reference a valid user")

    membership = BusinessMembership.get(user=user, business=g.current_business)
    if membership is None or membership.status == MembershipStatus.REMOVED.value:
        raise LookupError("assigned_to_user_id must reference a member of this business")

    return user


@leads_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_LEADS)
@db_session
def list_leads():
    stage_raw = (request.args.get("stage") or "").strip().lower()
    if stage_raw and stage_raw not in VALID_LEAD_STAGES:
        return _validation_error(
            "stage must be one of: new, interested, negotiating, booked, paid, lost"
        )

    assignee_id_raw = request.args.get("assignee_id")
    assignee_id = None
    if assignee_id_raw is not None:
        try:
            assignee_id = int(assignee_id_raw)
        except (TypeError, ValueError):
            return _validation_error("assignee_id must be an integer")

    leads = list(
        select(
            lead
            for lead in Lead
            if lead.business == g.current_business
            and (not stage_raw or lead.stage == stage_raw)
            and (assignee_id is None or lead.assigned_to_user.id == assignee_id)
        ).order_by(lambda lead: lead.created_at)
    )
    return jsonify({"leads": [lead.to_dict() for lead in reversed(leads)]}), 200


@leads_bp.post("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_LEADS)
@db_session
def create_lead():
    data = _json_body()
    conversation_id = data.get("conversation_id")
    if conversation_id is None:
        return _validation_error("conversation_id is required")

    try:
        conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return _validation_error("conversation_id must be an integer")

    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404

    try:
        next_stage = _validate_stage(data.get("stage", "new"))
        next_follow_up_at = _parse_optional_datetime(data.get("next_follow_up_at"))
        next_value = _coerce_optional_float(data.get("value"))
        assignee = _validate_assignee(data.get("assigned_to_user_id"))
    except ValueError as exc:
        return _validation_error(str(exc))
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404

    if data.get("source") is not None and not isinstance(data.get("source"), str):
        return _validation_error("source must be a string")
    if data.get("notes") is not None and not isinstance(data.get("notes"), str):
        return _validation_error("notes must be a string")

    payload = {
        "business": g.current_business,
        "conversation": conversation,
        "customer_id": conversation.customer_id,
        "stage": next_stage or "new",
        "value": next_value if next_value is not None else 0.0,
    }

    source = (data.get("source") or "").strip()
    if source:
        payload["source"] = source

    notes = (data.get("notes") or "").strip()
    if notes:
        payload["notes"] = notes

    if assignee is not None:
        payload["assigned_to_user"] = assignee

    if next_follow_up_at is not None:
        payload["next_follow_up_at"] = next_follow_up_at

    lead = Lead(**payload)
    commit()
    return jsonify({"lead": lead.to_dict()}), 201


@leads_bp.get("/<int:lead_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_LEADS)
@db_session
def get_lead(lead_id: int):
    lead = _lead_for_current_business(lead_id)
    if lead is None:
        return jsonify({"error": "Lead not found"}), 404

    return jsonify({"lead": lead.to_dict()}), 200


@leads_bp.patch("/<int:lead_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_LEADS)
@db_session
def update_lead(lead_id: int):
    lead = _lead_for_current_business(lead_id)
    if lead is None:
        return jsonify({"error": "Lead not found"}), 404

    data = _json_body()
    if not data:
        return jsonify({"lead": lead.to_dict()}), 200

    if "stage" in data:
        try:
            lead.stage = _validate_stage(data.get("stage")) or lead.stage
        except ValueError as exc:
            return _validation_error(str(exc))

    if "value" in data:
        try:
            lead.value = _coerce_optional_float(data.get("value"))
        except ValueError as exc:
            return _validation_error(str(exc))

    if "source" in data:
        source = data.get("source")
        if source is None:
            lead.source = None
        elif not isinstance(source, str):
            return _validation_error("source must be a string")
        else:
            lead.source = source.strip() or None

    if "notes" in data:
        notes = data.get("notes")
        if notes is None:
            lead.notes = None
        elif not isinstance(notes, str):
            return _validation_error("notes must be a string")
        else:
            lead.notes = notes.strip() or None

    if "assigned_to_user_id" in data:
        try:
            lead.assigned_to_user = _validate_assignee(data.get("assigned_to_user_id"))
        except ValueError as exc:
            return _validation_error(str(exc))
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404

    if "next_follow_up_at" in data:
        try:
            lead.next_follow_up_at = _parse_optional_datetime(data.get("next_follow_up_at"))
        except ValueError as exc:
            return _validation_error(str(exc))

    lead.updated_at = datetime.utcnow()
    commit()
    return jsonify({"lead": lead.to_dict()}), 200


@leads_bp.post("/<int:lead_id>/move-stage")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_LEADS)
@db_session
def move_lead_stage(lead_id: int):
    lead = _lead_for_current_business(lead_id)
    if lead is None:
        return jsonify({"error": "Lead not found"}), 404

    data = _json_body()
    stage = data.get("stage")
    if stage is None:
        return _validation_error("stage is required")

    try:
        lead.stage = _validate_stage(stage)
    except ValueError as exc:
        return _validation_error(str(exc))

    if lead.stage is None:
        return _validation_error("stage is required")

    lead.updated_at = datetime.utcnow()
    commit()
    return jsonify({"lead": lead.to_dict()}), 200
