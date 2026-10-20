from datetime import datetime, timezone

from flask import g, jsonify, request
from pony.orm import commit, db_session, select

from app.businesses.models import BusinessMembership
from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.conversations import conversations_bp
from app.conversations.models import Conversation
from app.users.models import User

VALID_CONVERSATION_STATUSES = frozenset({"open", "pending", "closed", "archived"})
VALID_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


def _not_found(message: str):
    return jsonify({"error": message}), 404


def _parse_int(value, field_name: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer")


def _parse_iso_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("Date values must be ISO-8601 datetime strings")
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Date values must be ISO-8601 datetime strings") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _normalize_tags(value):
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("tags must be an array of strings")
    cleaned = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("tags must be an array of strings")
        normalized = item.strip()
        if normalized:
            cleaned.append(normalized)
    return cleaned


def _conversation_for_current_business(conversation_id: int) -> Conversation | None:
    return Conversation.get(id=conversation_id, business=g.current_business)


def _conversation_payload(conversation: Conversation) -> dict:
    return conversation.to_dict()


def _validate_status(status):
    if status is None:
        return None
    normalized = str(status).strip().lower()
    if normalized not in VALID_CONVERSATION_STATUSES:
        raise ValueError(
            "status must be one of: open, pending, closed, archived"
        )
    return normalized


def _validate_priority(priority):
    if priority is None:
        return None
    normalized = str(priority).strip().lower()
    if normalized not in VALID_PRIORITIES:
        raise ValueError("priority must be one of: low, normal, high, urgent")
    return normalized


def _validate_assigned_to_user(user_id):
    if user_id is None:
        return None

    try:
        target_id = _parse_int(user_id, "assigned_to_user_id")
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    user = User.get(id=target_id)
    if user is None:
        raise LookupError("User not found")

    membership = BusinessMembership.get(user=user, business=g.current_business)
    if membership is None or membership.status != "active":
        raise LookupError("assigned_to_user_id must reference a member of this business")

    return user


def _validate_assigned_to_membership(membership_id):
    if membership_id is None:
        return None

    try:
        target_id = _parse_int(membership_id, "assigned_to_membership_id")
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    membership = BusinessMembership.get(id=target_id)
    if membership is None or membership.business.id != g.current_business.id:
        raise LookupError("assigned_to_membership_id must reference a member of this business")
    if membership.status != "active":
        raise LookupError("assigned_to_membership_id must reference an active member of this business")

    return membership


def _apply_assignment(conversation: Conversation, *, candidate_user=None, candidate_membership=None):
    if candidate_membership is not None:
        conversation.assigned_to_membership = candidate_membership
        conversation.assigned_to_user = candidate_membership.user
    elif candidate_user is not None:
        conversation.assigned_to_membership = None
        conversation.assigned_to_user = candidate_user
    else:
        conversation.assigned_to_membership = None
        conversation.assigned_to_user = None


def _conversation_sort_key(conversation: Conversation):
    if conversation.last_message_at is not None:
        return conversation.last_message_at
    return conversation.created_at


@conversations_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CONVERSATIONS)
@db_session
def list_conversations():
    status = (request.args.get("status") or "").strip().lower()
    priority = (request.args.get("priority") or "").strip().lower()
    channel = (request.args.get("channel") or "").strip().lower()
    tag = (request.args.get("tag") or "").strip().lower()
    search = (request.args.get("search") or "").strip()
    unread_raw = request.args.get("unread")

    if status and status not in VALID_CONVERSATION_STATUSES:
        return _validation_error(
            "status must be one of: open, pending, closed, archived"
        )
    if priority and priority not in VALID_PRIORITIES:
        return _validation_error("priority must be one of: low, normal, high, urgent")

    try:
        customer_id = (
            _parse_int(request.args.get("customer_id"), "customer_id")
            if request.args.get("customer_id") is not None
            else None
        )
        assigned_to_user_id = (
            _parse_int(request.args.get("assigned_to_user_id"), "assigned_to_user_id")
            if request.args.get("assigned_to_user_id") is not None
            else None
        )
        assigned_to_membership_id = (
            _parse_int(request.args.get("assigned_to_membership_id"), "assigned_to_membership_id")
            if request.args.get("assigned_to_membership_id") is not None
            else None
        )
    except ValueError as exc:
        return _validation_error(str(exc))

    from_date = None
    to_date = None
    for name in ("from_date", "date_from"):
        if request.args.get(name) is not None:
            try:
                from_date = _parse_iso_datetime(request.args.get(name))
            except ValueError as exc:
                return _validation_error(str(exc))
            break
    for name in ("to_date", "date_to"):
        if request.args.get(name) is not None:
            try:
                to_date = _parse_iso_datetime(request.args.get(name))
            except ValueError as exc:
                return _validation_error(str(exc))
            break

    unread = None
    if unread_raw is not None:
        normalized_unread = str(unread_raw).strip().lower()
        if normalized_unread not in {"true", "false"}:
            return _validation_error("unread must be either true or false")
        unread = normalized_unread == "true"

    conversations = list(
        select(
            conversation
            for conversation in Conversation
            if conversation.business == g.current_business
        )
    )

    filtered = []
    for conversation in conversations:
        if status and conversation.status != status:
            continue
        if priority and conversation.priority != priority:
            continue
        if channel and conversation.channel != channel:
            continue
        if customer_id is not None and conversation.customer_id != customer_id:
            continue
        if assigned_to_user_id is not None:
            if conversation.assigned_to_user is None or conversation.assigned_to_user.id != assigned_to_user_id:
                continue
        if assigned_to_membership_id is not None:
            if conversation.assigned_to_membership is None or conversation.assigned_to_membership.id != assigned_to_membership_id:
                continue
        if unread is not None:
            matches_unread = conversation.unread_count > 0
            if unread != matches_unread:
                continue
        if tag:
            normalized_tags = {item.strip().lower() for item in (conversation.tags_json or [])}
            if tag not in normalized_tags:
                continue
        if from_date or to_date:
            comparison_time = conversation.last_message_at or conversation.created_at
            if from_date and comparison_time < from_date:
                continue
            if to_date and comparison_time > to_date:
                continue
        if search:
            haystack = " ".join(
                [
                    str(conversation.customer_id),
                    conversation.channel,
                    conversation.status,
                    conversation.priority,
                    " ".join(conversation.tags_json or []),
                ]
            ).lower()
            if search.lower() not in haystack:
                continue
        filtered.append(conversation)

    filtered.sort(key=_conversation_sort_key, reverse=True)
    payload = [_conversation_payload(item) for item in filtered]
    return jsonify({"conversations": payload, "count": len(payload)}), 200


@conversations_bp.get("/<int:conversation_id>")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CONVERSATIONS)
@db_session
def get_conversation(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return _not_found("Conversation not found")
    return jsonify({"conversation": _conversation_payload(conversation)}), 200


@conversations_bp.patch("/<int:conversation_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def update_conversation(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return _not_found("Conversation not found")

    data = _json_body()
    if not data:
        return jsonify({"conversation": _conversation_payload(conversation)}), 200

    try:
        if "status" in data:
            conversation.status = _validate_status(data.get("status")) or conversation.status
        if "priority" in data:
            conversation.priority = _validate_priority(data.get("priority")) or conversation.priority
        if "tags" in data:
            tags = _normalize_tags(data.get("tags"))
            conversation.tags_json = tags if tags is not None else []
        if "channel" in data:
            channel = (data.get("channel") or "").strip().lower()
            if not channel:
                raise ValueError("channel cannot be empty")
            conversation.channel = channel
        if "customer_id" in data:
            conversation.customer_id = _parse_int(data.get("customer_id"), "customer_id")
        if "unread_count" in data:
            if data.get("unread_count") is None:
                conversation.unread_count = 0
            else:
                conversation.unread_count = int(data.get("unread_count"))
    except (ValueError, LookupError) as exc:
        return _validation_error(str(exc))

    conversation.updated_by = g.current_user
    conversation.updated_at = datetime.utcnow()
    commit()
    return jsonify({"conversation": _conversation_payload(conversation)}), 200


@conversations_bp.post("/<int:conversation_id>/assign")
@login_required
@business_required
@permission_required(PermissionKey.ASSIGN_CONVERSATIONS)
@db_session
def assign_conversation(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return _not_found("Conversation not found")

    data = _json_body()
    candidate_user = None
    candidate_membership = None

    if "assigned_to_user_id" in data:
        try:
            candidate_user = _validate_assigned_to_user(data.get("assigned_to_user_id"))
        except (ValueError, LookupError) as exc:
            return _validation_error(str(exc))

    if "assigned_to_membership_id" in data:
        try:
            candidate_membership = _validate_assigned_to_membership(
                data.get("assigned_to_membership_id")
            )
        except (ValueError, LookupError) as exc:
            return _validation_error(str(exc))

    if candidate_user is None and candidate_membership is None:
        return _validation_error("assigned_to_user_id or assigned_to_membership_id is required")

    if candidate_user is not None and candidate_membership is not None:
        if candidate_user.id != candidate_membership.user.id:
            return _validation_error(
                "assigned_to_user_id and assigned_to_membership_id do not match"
            )

    _apply_assignment(
        conversation,
        candidate_user=candidate_user,
        candidate_membership=candidate_membership,
    )
    conversation.updated_by = g.current_user
    conversation.updated_at = datetime.utcnow()
    commit()
    return jsonify({"conversation": _conversation_payload(conversation)}), 200


@conversations_bp.post("/<int:conversation_id>/unassign")
@login_required
@business_required
@permission_required(PermissionKey.ASSIGN_CONVERSATIONS)
@db_session
def unassign_conversation(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return _not_found("Conversation not found")

    conversation.assigned_to_user = None
    conversation.assigned_to_membership = None
    conversation.updated_by = g.current_user
    conversation.updated_at = datetime.utcnow()
    commit()
    return jsonify({"conversation": _conversation_payload(conversation)}), 200


@conversations_bp.post("/<int:conversation_id>/mark-read")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def mark_conversation_read(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return _not_found("Conversation not found")

    conversation.unread_count = 0
    conversation.updated_by = g.current_user
    conversation.updated_at = datetime.utcnow()
    commit()
    return jsonify({"conversation": _conversation_payload(conversation)}), 200


@conversations_bp.post("/<int:conversation_id>/archive")
@login_required
@business_required
@permission_required(PermissionKey.CLOSE_CONVERSATIONS)
@db_session
def archive_conversation(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return _not_found("Conversation not found")

    conversation.status = "archived"
    conversation.closed_at = datetime.utcnow()
    conversation.updated_by = g.current_user
    conversation.updated_at = datetime.utcnow()
    commit()
    return jsonify({"conversation": _conversation_payload(conversation)}), 200


@conversations_bp.post("/<int:conversation_id>/close")
@login_required
@business_required
@permission_required(PermissionKey.CLOSE_CONVERSATIONS)
@db_session
def close_conversation(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return _not_found("Conversation not found")

    conversation.status = "closed"
    conversation.closed_at = datetime.utcnow()
    conversation.updated_by = g.current_user
    conversation.updated_at = datetime.utcnow()
    commit()
    return jsonify({"conversation": _conversation_payload(conversation)}), 200


@conversations_bp.post("/<int:conversation_id>/reopen")
@login_required
@business_required
@permission_required(PermissionKey.CLOSE_CONVERSATIONS)
@db_session
def reopen_conversation(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return _not_found("Conversation not found")

    conversation.status = "open"
    conversation.closed_at = None
    conversation.updated_by = g.current_user
    conversation.updated_at = datetime.utcnow()
    commit()
    return jsonify({"conversation": _conversation_payload(conversation)}), 200
