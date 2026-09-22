from datetime import datetime, timezone

from flask import g, jsonify, request
from pony.orm import commit, db_session, select

from app.automations.engine import dispatch_automation_event
from app.bookings import bookings_bp
from app.bookings.models import Booking, VALID_BOOKING_STATUSES
from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.conversations.models import Conversation
from app.customers.models import Customer


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


def _booking_for_current_business(booking_id: int) -> Booking | None:
    return Booking.get(id=booking_id, business=g.current_business)


def _parse_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _parse_scheduled_at(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("scheduled_at must be an ISO-8601 datetime string") from exc
    else:
        raise ValueError("scheduled_at is required")

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _validate_status(value) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in VALID_BOOKING_STATUSES:
        raise ValueError(
            "status must be one of: pending, confirmed, completed, cancelled, no_show"
        )
    return normalized


def _validate_service_name(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("service_name is required")
    return value.strip()


def _validate_duration(value) -> int:
    duration = _parse_int(value, "duration_minutes")
    if duration <= 0:
        raise ValueError("duration_minutes must be greater than 0")
    return duration


def _customer_for_current_business(customer_id: int) -> Customer | None:
    return Customer.get(id=customer_id, business=g.current_business)


def _conversation_for_current_business(conversation_id: int) -> Conversation | None:
    return Conversation.get(id=conversation_id, business=g.current_business)


def _validate_conversation_customer(
    conversation: Conversation | None,
    customer_id: int,
) -> None:
    if conversation is not None and conversation.customer_id != customer_id:
        raise ValueError("conversation_id must belong to the selected customer")


def _parse_optional_notes(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("notes must be a string")
    return value.strip() or None


@bookings_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_BOOKINGS)
@db_session
def list_bookings():
    status = (request.args.get("status") or "").strip().lower()
    if status and status not in VALID_BOOKING_STATUSES:
        return _validation_error(
            "status must be one of: pending, confirmed, completed, cancelled, no_show"
        )

    try:
        customer_id = (
            _parse_int(request.args.get("customer_id"), "customer_id")
            if request.args.get("customer_id") is not None
            else None
        )
        conversation_id = (
            _parse_int(request.args.get("conversation_id"), "conversation_id")
            if request.args.get("conversation_id") is not None
            else None
        )
    except ValueError as exc:
        return _validation_error(str(exc))

    bookings = list(
        select(
            booking
            for booking in Booking
            if booking.business == g.current_business
            and (not status or booking.status == status)
            and (customer_id is None or booking.customer_id == customer_id)
            and (
                conversation_id is None
                or (
                    booking.conversation is not None
                    and booking.conversation.id == conversation_id
                )
            )
        ).order_by(lambda booking: booking.scheduled_at)
    )
    return jsonify({"bookings": [booking.to_dict() for booking in bookings]}), 200


@bookings_bp.post("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_BOOKINGS)
@db_session
def create_booking():
    data = _json_body()

    if data.get("customer_id") is None:
        return _validation_error("customer_id is required")
    if data.get("duration_minutes") is None:
        return _validation_error("duration_minutes is required")

    try:
        customer_id = _parse_int(data.get("customer_id"), "customer_id")
        service_name = _validate_service_name(data.get("service_name"))
        scheduled_at = _parse_scheduled_at(data.get("scheduled_at"))
        duration_minutes = _validate_duration(data.get("duration_minutes"))
        status = _validate_status(data.get("status", "pending"))
        notes = _parse_optional_notes(data.get("notes"))
    except ValueError as exc:
        return _validation_error(str(exc))

    customer = _customer_for_current_business(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404

    conversation = None
    if data.get("conversation_id") is not None:
        try:
            conversation_id = _parse_int(data.get("conversation_id"), "conversation_id")
        except ValueError as exc:
            return _validation_error(str(exc))
        conversation = _conversation_for_current_business(conversation_id)
        if conversation is None:
            return jsonify({"error": "Conversation not found"}), 404
        try:
            _validate_conversation_customer(conversation, customer_id)
        except ValueError as exc:
            return _validation_error(str(exc))

    booking = Booking(
        business=g.current_business,
        customer_id=customer.id,
        conversation=conversation,
        service_name=service_name,
        scheduled_at=scheduled_at,
        duration_minutes=duration_minutes,
        status=status,
        notes=notes,
    )
    commit()

    dispatch_automation_event(
        g.current_business,
        "booking_created",
        {
            "booking_id": booking.id,
            "customer_id": booking.customer_id,
            "conversation_id": booking.conversation.id if booking.conversation else None,
            "service_name": booking.service_name,
            "scheduled_at": booking.scheduled_at.isoformat() + "Z",
            "duration_minutes": booking.duration_minutes,
            "status": booking.status,
        },
    )

    return jsonify({"booking": booking.to_dict()}), 201


@bookings_bp.get("/<int:booking_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_BOOKINGS)
@db_session
def get_booking(booking_id: int):
    booking = _booking_for_current_business(booking_id)
    if booking is None:
        return jsonify({"error": "Booking not found"}), 404
    return jsonify({"booking": booking.to_dict()}), 200


@bookings_bp.patch("/<int:booking_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_BOOKINGS)
@db_session
def update_booking(booking_id: int):
    booking = _booking_for_current_business(booking_id)
    if booking is None:
        return jsonify({"error": "Booking not found"}), 404

    data = _json_body()
    if not data:
        return jsonify({"booking": booking.to_dict()}), 200

    customer_id = booking.customer_id
    conversation = booking.conversation

    try:
        if "customer_id" in data:
            if data.get("customer_id") is None:
                raise ValueError("customer_id is required")
            customer_id = _parse_int(data.get("customer_id"), "customer_id")
            customer = _customer_for_current_business(customer_id)
            if customer is None:
                return jsonify({"error": "Customer not found"}), 404

        if "conversation_id" in data:
            if data.get("conversation_id") is None:
                conversation = None
            else:
                conversation_id = _parse_int(data.get("conversation_id"), "conversation_id")
                conversation = _conversation_for_current_business(conversation_id)
                if conversation is None:
                    return jsonify({"error": "Conversation not found"}), 404

        _validate_conversation_customer(conversation, customer_id)

        if "service_name" in data:
            booking.service_name = _validate_service_name(data.get("service_name"))
        if "scheduled_at" in data:
            booking.scheduled_at = _parse_scheduled_at(data.get("scheduled_at"))
        if "duration_minutes" in data:
            booking.duration_minutes = _validate_duration(data.get("duration_minutes"))
        if "status" in data:
            booking.status = _validate_status(data.get("status"))
        if "notes" in data:
            booking.notes = _parse_optional_notes(data.get("notes"))
    except ValueError as exc:
        return _validation_error(str(exc))

    booking.customer_id = customer_id
    booking.conversation = conversation
    booking.updated_at = datetime.utcnow()
    commit()
    return jsonify({"booking": booking.to_dict()}), 200


@bookings_bp.delete("/<int:booking_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_BOOKINGS)
@db_session
def delete_booking(booking_id: int):
    booking = _booking_for_current_business(booking_id)
    if booking is None:
        return jsonify({"error": "Booking not found"}), 404

    booking.delete()
    commit()
    return "", 204