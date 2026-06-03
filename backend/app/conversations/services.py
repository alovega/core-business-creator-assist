from __future__ import annotations

from datetime import UTC, datetime

from app.common.db_errors import is_unique_violation
from app.businesses.membership_status import MembershipStatus
from app.businesses.models import BusinessMembership
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.users.models import User

ALLOWED_CHANNELS = frozenset({"whatsapp", "instagram", "facebook", "sms", "email"})
ALLOWED_STATUSES = frozenset({"open", "pending", "resolved", "closed", "archived"})
ALLOWED_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _normalize_channel(channel: str | None) -> str:
    value = (channel or "whatsapp").strip().lower()
    if value not in ALLOWED_CHANNELS:
        raise ValueError(f"Unsupported channel: {value}")
    return value


def _normalize_status(status: str | None) -> str:
    value = (status or "open").strip().lower()
    if value not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported status: {value}")
    return value


def _normalize_priority(priority: str | None) -> str:
    value = (priority or "normal").strip().lower()
    if value not in ALLOWED_PRIORITIES:
        raise ValueError(f"Unsupported priority: {value}")
    return value


def find_or_create_conversation(*, business, customer, channel: str = "whatsapp"):
    channel = _normalize_channel(channel)
    conversation = Conversation.get(
        business=business,
        customer=customer,
        channel=channel,
    )
    if conversation is not None:
        return conversation, False

    now = _utcnow_naive()
    try:
        conversation = Conversation(
            business=business,
            customer=customer,
            channel=channel,
            status="open",
            priority="normal",
            unread_count=0,
            tags_json=[],
            last_message_at=now,
            created_at=now,
            updated_at=now,
        )
        return conversation, True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if not is_unique_violation(exc):
            raise
        existing = Conversation.get(
            business=business,
            customer=customer,
            channel=channel,
        )
        if existing is None:
            raise
        return existing, False


def list_conversations(
    *,
    business,
    filters: dict | None = None,
    page: int = 1,
    per_page: int = 20,
):
    filters = filters or {}
    page = max(1, page)
    per_page = min(100, max(1, per_page))
    offset = (page - 1) * per_page

    candidates = [c for c in Conversation.select() if c.business.id == business.id]

    status = (filters.get("status") or "").strip().lower()
    assigned_to = filters.get("assigned_to")
    channel = (filters.get("channel") or "").strip().lower()
    customer_id = filters.get("customer_id")
    tag = (filters.get("tag") or "").strip().lower()
    priority = (filters.get("priority") or "").strip().lower()
    search = (filters.get("search") or "").strip().lower()
    unread = filters.get("unread")
    from_date = filters.get("from")
    to_date = filters.get("to")

    def _matches(conversation) -> bool:
        if status and conversation.status != status:
            return False
        if channel and conversation.channel != channel:
            return False
        if customer_id and conversation.customer.id != int(customer_id):
            return False
        if priority and conversation.priority != priority:
            return False
        if tag and tag not in [str(v).lower() for v in (conversation.tags_json or [])]:
            return False
        if assigned_to is not None and assigned_to != "":
            if str(assigned_to).lower() == "none":
                if conversation.assigned_to is not None or conversation.assigned_user is not None:
                    return False
            else:
                target_id = int(assigned_to)
                membership_id = conversation.assigned_to.id if conversation.assigned_to else None
                user_id = conversation.assigned_user.id if conversation.assigned_user else None
                if target_id not in {membership_id, user_id}:
                    return False
        if unread is True and int(conversation.unread_count or 0) <= 0:
            return False
        if unread is False and int(conversation.unread_count or 0) > 0:
            return False
        if from_date and conversation.updated_at < from_date:
            return False
        if to_date and conversation.updated_at > to_date:
            return False
        if not search:
            return True
        name = (conversation.customer.name or "").lower()
        phone = (conversation.customer.phone_number or "").lower()
        return search in name or search in phone

    filtered = [conversation for conversation in candidates if _matches(conversation)]
    filtered.sort(
        key=lambda c: (c.last_message_at or c.updated_at or c.created_at),
        reverse=True,
    )
    total = len(filtered)
    return filtered[offset : offset + per_page], total


def get_conversation_for_business(*, business, conversation_id: int):
    return Conversation.get(id=conversation_id, business=business)


def resolve_conversation_for_customer(
    *,
    business,
    customer,
    channel: str,
    actor=None,
):
    if Customer.get(id=customer.id, business=business) is None:
        raise ValueError("Customer not found in this business")
    conversation, created = find_or_create_conversation(
        business=business,
        customer=customer,
        channel=channel,
    )
    if conversation.status in {"resolved", "closed", "archived"}:
        conversation.status = "open"
        conversation.closed_at = None
        conversation.updated_by = actor
        conversation.updated_at = _utcnow_naive()
    return conversation, created


def update_conversation(
    *,
    conversation,
    actor,
    updates: dict,
):
    if "status" in updates:
        next_status = _normalize_status(updates.get("status"))
        conversation.status = next_status
        if next_status in {"closed", "archived", "resolved"}:
            conversation.closed_at = _utcnow_naive()
        elif next_status == "open":
            conversation.closed_at = None
    if "priority" in updates and updates.get("priority") is not None:
        conversation.priority = _normalize_priority(updates.get("priority"))
    if "tags" in updates:
        tags = updates.get("tags") or []
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in tags:
            if not isinstance(raw, str):
                continue
            value = raw.strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)
        conversation.tags_json = cleaned
    conversation.updated_by = actor
    conversation.updated_at = _utcnow_naive()
    return conversation


def assign_conversation(
    *,
    conversation,
    business,
    actor,
    membership_id: int | None = None,
    user_id: int | None = None,
):
    if membership_id is None and user_id is None:
        raise ValueError("membership_id or user_id is required")

    target_membership = None
    target_user = None
    if membership_id is not None:
        target_membership = BusinessMembership.get(id=membership_id, business=business)
        if target_membership is None:
            raise ValueError("Business membership not found")
        if target_membership.status != MembershipStatus.ACTIVE.value:
            raise ValueError("Business membership is not active")
    else:
        target_user = User.get(id=user_id)
        if target_user is None:
            raise ValueError("User not found")
        membership = BusinessMembership.get(user=target_user, business=business)
        if membership is None or membership.status != MembershipStatus.ACTIVE.value:
            raise ValueError("User does not have an active business membership")
        target_membership = membership

    conversation.assigned_to = target_membership
    conversation.assigned_user = target_user
    conversation.updated_by = actor
    conversation.updated_at = _utcnow_naive()
    return conversation


def unassign_conversation(*, conversation, actor):
    conversation.assigned_to = None
    conversation.assigned_user = None
    conversation.updated_by = actor
    conversation.updated_at = _utcnow_naive()
    return conversation


def mark_read(*, conversation, actor):
    conversation.unread_count = 0
    conversation.updated_by = actor
    conversation.updated_at = _utcnow_naive()
    return conversation


def mark_inbound_activity(*, conversation, occurred_at: datetime | None = None):
    timestamp = occurred_at or _utcnow_naive()
    conversation.last_message_at = timestamp
    conversation.unread_count = max(0, int(conversation.unread_count or 0)) + 1
    conversation.updated_at = _utcnow_naive()
    return conversation
