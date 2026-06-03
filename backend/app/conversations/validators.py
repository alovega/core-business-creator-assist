from __future__ import annotations

from datetime import datetime

from app.conversations.services import ALLOWED_CHANNELS, ALLOWED_PRIORITIES, ALLOWED_STATUSES


def _clean_optional_string(value, *, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if max_len is not None:
        stripped = stripped[:max_len]
    return stripped


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"


def serialize_conversation(conversation) -> dict:
    return {
        "id": conversation.id,
        "business_id": conversation.business.id,
        "customer_id": conversation.customer.id,
        "channel": conversation.channel,
        "status": conversation.status,
        "assigned_membership_id": conversation.assigned_to.id if conversation.assigned_to else None,
        "assigned_user_id": conversation.assigned_user.id if conversation.assigned_user else None,
        "last_message_at": serialize_datetime(conversation.last_message_at),
        "unread_count": int(conversation.unread_count or 0),
        "tags": list(conversation.tags_json or []),
        "priority": conversation.priority,
        "created_by_id": conversation.created_by.id if conversation.created_by else None,
        "updated_by_id": conversation.updated_by.id if conversation.updated_by else None,
        "created_at": serialize_datetime(conversation.created_at),
        "updated_at": serialize_datetime(conversation.updated_at),
        "closed_at": serialize_datetime(conversation.closed_at),
        "customer": {
            "id": conversation.customer.id,
            "name": conversation.customer.name,
            "phone_number": conversation.customer.phone_number,
        },
    }


def parse_list_filters(args) -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    filters: dict = {}

    status = _clean_optional_string(args.get("status"))
    if status:
        status = status.lower()
        if status not in ALLOWED_STATUSES:
            errors["status"] = (
                f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"
            )
        else:
            filters["status"] = status

    channel = _clean_optional_string(args.get("channel"))
    if channel:
        channel = channel.lower()
        if channel not in ALLOWED_CHANNELS:
            errors["channel"] = (
                f"channel must be one of: {', '.join(sorted(ALLOWED_CHANNELS))}"
            )
        else:
            filters["channel"] = channel

    priority = _clean_optional_string(args.get("priority"))
    if priority:
        priority = priority.lower()
        if priority not in ALLOWED_PRIORITIES:
            errors["priority"] = (
                f"priority must be one of: {', '.join(sorted(ALLOWED_PRIORITIES))}"
            )
        else:
            filters["priority"] = priority

    assigned_to = _clean_optional_string(args.get("assigned_to"))
    if assigned_to:
        if assigned_to.lower() == "none":
            filters["assigned_to"] = "none"
        else:
            try:
                filters["assigned_to"] = int(assigned_to)
            except ValueError:
                errors["assigned_to"] = "assigned_to must be an integer id or 'none'"

    customer_id = _clean_optional_string(args.get("customer_id"))
    if customer_id:
        try:
            filters["customer_id"] = int(customer_id)
        except ValueError:
            errors["customer_id"] = "customer_id must be an integer"

    unread = _clean_optional_string(args.get("unread"))
    if unread:
        normalized = unread.lower()
        if normalized in {"1", "true", "yes"}:
            filters["unread"] = True
        elif normalized in {"0", "false", "no"}:
            filters["unread"] = False
        else:
            errors["unread"] = "unread must be one of: true, false"

    tag = _clean_optional_string(args.get("tag"))
    if tag:
        filters["tag"] = tag.lower()

    search = _clean_optional_string(args.get("search"), max_len=255)
    if search:
        filters["search"] = search.lower()

    for key, param_name in (("from", "from"), ("to", "to")):
        raw = _clean_optional_string(args.get(param_name))
        if not raw:
            continue
        try:
            filters[key] = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
        except ValueError:
            errors[param_name] = f"{param_name} must be an ISO datetime"

    return filters, errors


def validate_patch_payload(data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not data:
        errors["_form"] = "At least one field is required"
        return errors

    if "status" in data:
        status = _clean_optional_string(data.get("status"))
        if not status:
            errors["status"] = "status must be a non-empty string"
        elif status.lower() not in ALLOWED_STATUSES:
            errors["status"] = f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"

    if "priority" in data:
        priority = _clean_optional_string(data.get("priority"))
        if not priority:
            errors["priority"] = "priority must be a non-empty string"
        elif priority.lower() not in ALLOWED_PRIORITIES:
            errors["priority"] = (
                f"priority must be one of: {', '.join(sorted(ALLOWED_PRIORITIES))}"
            )

    if "tags" in data:
        tags = data.get("tags")
        if tags is not None and (
            not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags)
        ):
            errors["tags"] = "tags must be an array of strings"

    return errors

