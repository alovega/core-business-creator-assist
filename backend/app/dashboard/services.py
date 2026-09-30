from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from pony.orm import count, select, sum as pony_sum

from app.bookings.models import Booking, VALID_BOOKING_STATUSES
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.leads.models import Lead, VALID_LEAD_STAGES
from app.messages.models import Message
from app.payments.models import Payment, VALID_PAYMENT_STATUSES


@dataclass(frozen=True)
class DateRange:
    """UTC, naive, half-open range: [start, end)."""

    start: datetime
    end: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "start": self.start.isoformat() + "Z",
            "end": self.end.isoformat() + "Z",
        }


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_boundary(raw: str, *, is_end: bool) -> datetime:
    value = raw.strip()
    if not value:
        raise ValueError("Date values cannot be empty")

    # A date-only end value is inclusive from the API consumer's perspective,
    # so turn it into the next midnight and keep DB predicates half-open.
    try:
        parsed_date = date.fromisoformat(value)
        if len(value) == 10:
            boundary = datetime.combine(parsed_date, time.min)
            return boundary + timedelta(days=1) if is_end else boundary
    except ValueError:
        pass

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "start_date and end_date must be ISO-8601 dates or datetimes"
        ) from exc
    return _to_utc_naive(parsed)


def parse_date_range(
    start_raw: str | None,
    end_raw: str | None,
    *,
    now: datetime | None = None,
) -> DateRange:
    """Return a UTC range, defaulting to the current UTC day."""

    current = _to_utc_naive(now or datetime.utcnow())
    today = current.date()

    start = (
        _parse_boundary(start_raw, is_end=False)
        if start_raw
        else datetime.combine(today, time.min)
    )
    end = (
        _parse_boundary(end_raw, is_end=True)
        if end_raw
        else datetime.combine(today + timedelta(days=1), time.min)
    )

    if start >= end:
        raise ValueError("start_date must be before end_date")
    return DateRange(start=start, end=end)


def _round_seconds(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def average_response_time_seconds(business, date_range: DateRange) -> float | None:
    """
    Average first-response time for customer messages in the selected range.

    One ordered query is used (no per-conversation/N+1 queries). For each
    conversation, a run of incoming messages starts a waiting period and the
    first subsequent outgoing message closes it. This measures the business's
    first response to a customer burst rather than counting multiple agent
    messages as separate responses.
    """

    messages = list(
        select(
            message
            for message in Message
            if message.business == business
            and message.created_at >= date_range.start
            and message.created_at < date_range.end
            and message.direction in ("incoming", "outgoing")
        ).order_by(lambda message: (message.conversation.id, message.created_at, message.id))
    )

    waiting_since: dict[int, datetime] = {}
    response_times: list[float] = []

    for message in messages:
        conversation_id = message.conversation.id
        if message.direction == "incoming":
            waiting_since.setdefault(conversation_id, message.created_at)
            continue

        started_at = waiting_since.pop(conversation_id, None)
        if started_at is not None and message.created_at >= started_at:
            response_times.append((message.created_at - started_at).total_seconds())

    if not response_times:
        return None
    return _round_seconds(sum(response_times) / len(response_times))


def conversation_metrics(business, date_range: DateRange) -> dict:
    scoped = select(
        conversation
        for conversation in Conversation
        if conversation.business == business
        and conversation.updated_at >= date_range.start
        and conversation.updated_at < date_range.end
    )

    by_status = {
        status: count(
            conversation
            for conversation in Conversation
            if conversation.business == business
            and conversation.updated_at >= date_range.start
            and conversation.updated_at < date_range.end
            and conversation.status == status
        )
        for status in ("open", "pending", "closed", "archived")
    }

    unread_conversations = count(
        conversation
        for conversation in Conversation
        if conversation.business == business
        and conversation.updated_at >= date_range.start
        and conversation.updated_at < date_range.end
        and conversation.unread_count > 0
    )
    unread_messages = pony_sum(
        conversation.unread_count
        for conversation in Conversation
        if conversation.business == business
        and conversation.updated_at >= date_range.start
        and conversation.updated_at < date_range.end
    ) or 0

    return {
        "total": scoped.count(),
        "unread_conversations": unread_conversations,
        "unread_messages": unread_messages,
        "by_status": by_status,
        "average_response_time_seconds": average_response_time_seconds(
            business, date_range
        ),
    }


def lead_metrics(business, date_range: DateRange) -> dict:
    scoped = select(
        lead
        for lead in Lead
        if lead.business == business
        and lead.created_at >= date_range.start
        and lead.created_at < date_range.end
    )

    by_stage = {
        stage: count(
            lead
            for lead in Lead
            if lead.business == business
            and lead.created_at >= date_range.start
            and lead.created_at < date_range.end
            and lead.stage == stage
        )
        for stage in sorted(VALID_LEAD_STAGES)
    }
    total_value = pony_sum(
        lead.value
        for lead in Lead
        if lead.business == business
        and lead.created_at >= date_range.start
        and lead.created_at < date_range.end
        and lead.value is not None
    ) or 0.0

    return {
        "total": scoped.count(),
        "by_stage": by_stage,
        "total_value": round(float(total_value), 2),
    }


def booking_metrics(business, date_range: DateRange) -> dict:
    # Operational dashboard: bookings are filtered by when they are scheduled,
    # not by when the record happened to be created.
    scoped = select(
        booking
        for booking in Booking
        if booking.business == business
        and booking.scheduled_at >= date_range.start
        and booking.scheduled_at < date_range.end
    )

    return {
        "total": scoped.count(),
        "by_status": {
            status: count(
                booking
                for booking in Booking
                if booking.business == business
                and booking.scheduled_at >= date_range.start
                and booking.scheduled_at < date_range.end
                and booking.status == status
            )
            for status in sorted(VALID_BOOKING_STATUSES)
        },
    }


def payment_metrics(business, date_range: DateRange) -> dict:
    payments = list(
        select(
            payment
            for payment in Payment
            if payment.business == business
            and payment.created_at >= date_range.start
            and payment.created_at < date_range.end
        )
    )

    by_status = {status: 0 for status in sorted(VALID_PAYMENT_STATUSES)}
    totals_by_currency: dict[str, Decimal] = {}
    paid_by_currency: dict[str, Decimal] = {}

    for payment in payments:
        by_status[payment.status] = by_status.get(payment.status, 0) + 1
        totals_by_currency[payment.currency] = (
            totals_by_currency.get(payment.currency, Decimal("0")) + payment.amount
        )
        if payment.status == "paid":
            paid_by_currency[payment.currency] = (
                paid_by_currency.get(payment.currency, Decimal("0")) + payment.amount
            )

    return {
        "total": len(payments),
        "pending": by_status.get("pending", 0),
        "by_status": by_status,
        "totals_by_currency": {
            currency: format(amount, "f")
            for currency, amount in sorted(totals_by_currency.items())
        },
        "paid_by_currency": {
            currency: format(amount, "f")
            for currency, amount in sorted(paid_by_currency.items())
        },
    }


def summary_metrics(business, date_range: DateRange) -> dict:
    """
    Dashboard card metrics.

    unread_conversations and active_customers are current-state snapshots.
    Leads, bookings, payments and response-time are filtered by date_range.
    """

    unread_conversations = count(
        conversation
        for conversation in Conversation
        if conversation.business == business and conversation.unread_count > 0
    )
    new_leads = count(
        lead
        for lead in Lead
        if lead.business == business
        and lead.created_at >= date_range.start
        and lead.created_at < date_range.end
    )
    bookings = count(
        booking
        for booking in Booking
        if booking.business == business
        and booking.scheduled_at >= date_range.start
        and booking.scheduled_at < date_range.end
    )
    pending_payments = count(
        payment
        for payment in Payment
        if payment.business == business
        and payment.status == "pending"
        and payment.created_at >= date_range.start
        and payment.created_at < date_range.end
    )
    active_customers = count(
        customer
        for customer in Customer
        if customer.business == business and customer.status == "active"
    )

    return {
        "unread_conversations": unread_conversations,
        "new_leads": new_leads,
        "bookings": bookings,
        "pending_payments": pending_payments,
        "average_response_time_seconds": average_response_time_seconds(
            business, date_range
        ),
        "active_customers": active_customers,
    }