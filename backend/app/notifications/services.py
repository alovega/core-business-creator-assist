from __future__ import annotations

import json
from typing import Iterable

from pony.orm import commit, select

import app.extensions as extensions
from app.businesses.membership_status import MembershipStatus
from app.businesses.models import BusinessMembership
from app.common.logging import get_logger
from app.notifications.models import Notification

logger = get_logger("app.notifications")


NOTIFICATION_NEW_MESSAGE = "new_message"
NOTIFICATION_NEW_LEAD = "new_lead"
NOTIFICATION_BOOKING_CREATED = "booking_created"
NOTIFICATION_PAYMENT_PENDING = "payment_pending"
NOTIFICATION_AUTOMATION_FAILED = "automation_failed"


def create_notification(
    *,
    business,
    user,
    title: str,
    message: str,
    notification_type: str,
    link_url: str | None = None,
) -> Notification:
    return Notification(
        business=business,
        user=user,
        title=title.strip(),
        message=message.strip(),
        type=notification_type.strip(),
        link_url=link_url,
    )


def notify_business_staff(
    *,
    business,
    title: str,
    message: str,
    notification_type: str,
    link_url: str | None = None,
    user_ids: Iterable[int] | None = None,
) -> list[Notification]:
    """Persist one notification per active business member.

    `user_ids` can narrow delivery while preserving business membership scoping.
    """
    requested_user_ids = set(user_ids) if user_ids is not None else None
    memberships = list(
        select(
            membership
            for membership in BusinessMembership
            if membership.business == business
            and membership.status == MembershipStatus.ACTIVE.value
        )
    )

    notifications = [
        create_notification(
            business=business,
            user=membership.user,
            title=title,
            message=message,
            notification_type=notification_type,
            link_url=link_url,
        )
        for membership in memberships
        if requested_user_ids is None or membership.user.id in requested_user_ids
    ]
    commit()

    if notifications and extensions.redis_client is not None:
        try:
            extensions.redis_client.publish(
                f"business:{business.id}:notifications",
                json.dumps(
                    {
                        "type": notification_type,
                        "business_id": business.id,
                        "recipient_user_ids": [item.user.id for item in notifications],
                        "notification_ids": [item.id for item in notifications],
                        "title": title,
                        "message": message,
                        "link_url": link_url,
                    }
                ),
            )
        except Exception:
            # Persistence is the source of truth; realtime delivery is best-effort.
            logger.exception(
                "notification_publish_failed",
                business_id=business.id,
                notification_type=notification_type,
            )

    return notifications


def notify_new_message(message) -> list[Notification]:
    if message.direction != "incoming":
        return []
    preview = (message.body or "").strip()
    text = preview[:160] if preview else f"New {message.message_type} message received"
    return notify_business_staff(
        business=message.business,
        title="New message",
        message=text,
        notification_type=NOTIFICATION_NEW_MESSAGE,
        link_url=f"/conversations/{message.conversation.id}",
    )


def notify_new_lead(lead) -> list[Notification]:
    return notify_business_staff(
        business=lead.business,
        title="New lead",
        message=f"Lead #{lead.id} was created.",
        notification_type=NOTIFICATION_NEW_LEAD,
        link_url=f"/leads/{lead.id}",
    )


def notify_booking_created(booking) -> list[Notification]:
    return notify_business_staff(
        business=booking.business,
        title="Booking created",
        message=f"{booking.service_name} booking was created.",
        notification_type=NOTIFICATION_BOOKING_CREATED,
        link_url=f"/bookings/{booking.id}",
    )


def notify_payment_pending(payment) -> list[Notification]:
    return notify_business_staff(
        business=payment.business,
        title="Payment pending",
        message=f"{payment.currency} {format(payment.amount, 'f')} payment is pending.",
        notification_type=NOTIFICATION_PAYMENT_PENDING,
        link_url=f"/payments/{payment.id}",
    )


def notify_automation_failed(*, business, automation, error_message: str) -> list[Notification]:
    error = (error_message or "Automation execution failed").strip()
    return notify_business_staff(
        business=business,
        title="Automation failed",
        message=f"{automation.name}: {error[:500]}",
        notification_type=NOTIFICATION_AUTOMATION_FAILED,
        link_url=f"/automations/{automation.id}",
    )