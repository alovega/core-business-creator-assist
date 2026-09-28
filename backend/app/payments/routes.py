from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import g, jsonify, request
from pony.orm import commit, db_session, desc, select

from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.conversations.models import Conversation
from app.customers.models import Customer
from app.messages.models import Message
from app.messages.services import WhatsAppSendError, send_whatsapp_message
from app.payments import payments_bp
from app.payments.models import Payment, VALID_PAYMENT_METHODS, VALID_PAYMENT_STATUSES


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


def _parse_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _parse_amount(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("amount must be a valid number") from exc
    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    return amount.quantize(Decimal("0.01"))


def _validate_currency(value) -> str:
    currency = str(value or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a 3-letter ISO currency code")
    return currency


def _validate_method(value) -> str:
    method = str(value or "").strip().lower()
    if method not in VALID_PAYMENT_METHODS:
        raise ValueError("method must be one of: cash, mpesa, bank_transfer, card, other")
    return method


def _validate_status(value) -> str:
    status = str(value or "").strip().lower()
    if status not in VALID_PAYMENT_STATUSES:
        raise ValueError("status must be one of: pending, paid, failed, cancelled")
    return status


def _optional_text(value, field: str):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value.strip() or None


def _payment_for_current_business(payment_id: int) -> Payment | None:
    return Payment.get(id=payment_id, business=g.current_business)


def _customer_for_current_business(customer_id: int) -> Customer | None:
    return Customer.get(id=customer_id, business=g.current_business)


def _conversation_for_current_business(conversation_id: int) -> Conversation | None:
    return Conversation.get(id=conversation_id, business=g.current_business)


def _validate_conversation_customer(conversation: Conversation | None, customer_id: int) -> None:
    if conversation is not None and conversation.customer_id != customer_id:
        raise ValueError("conversation_id must belong to the selected customer")


def _set_status(payment: Payment, status: str) -> None:
    payment.status = status
    if status == "paid":
        if payment.confirmed_at is None:
            payment.confirmed_at = datetime.utcnow()
            payment.confirmed_by_user = g.current_user
    else:
        payment.confirmed_at = None
        payment.confirmed_by_user = None


def _reminder_conversation(payment: Payment) -> Conversation | None:
    if payment.conversation is not None:
        return payment.conversation
    matches = list(
        select(
            conversation
            for conversation in Conversation
            if conversation.business == g.current_business
            and conversation.customer_id == payment.customer_id
            and conversation.channel == "whatsapp"
        ).order_by(lambda conversation: desc(conversation.updated_at))[:1]
    )
    return matches[0] if matches else None


@payments_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_PAYMENTS)
@db_session
def list_payments():
    status = (request.args.get("status") or "").strip().lower()
    if status and status not in VALID_PAYMENT_STATUSES:
        return _validation_error("status must be one of: pending, paid, failed, cancelled")

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

    payments = list(
        select(
            payment
            for payment in Payment
            if payment.business == g.current_business
            and (not status or payment.status == status)
            and (customer_id is None or payment.customer_id == customer_id)
            and (
                conversation_id is None
                or (
                    payment.conversation is not None
                    and payment.conversation.id == conversation_id
                )
            )
        ).order_by(lambda payment: desc(payment.created_at))
    )
    return jsonify({"payments": [payment.to_dict() for payment in payments]}), 200


@payments_bp.post("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_PAYMENTS)
@db_session
def create_payment():
    data = _json_body()
    if data.get("customer_id") is None:
        return _validation_error("customer_id is required")
    if data.get("amount") is None:
        return _validation_error("amount is required")

    try:
        customer_id = _parse_int(data.get("customer_id"), "customer_id")
        amount = _parse_amount(data.get("amount"))
        currency = _validate_currency(data.get("currency"))
        method = _validate_method(data.get("method"))
        status = _validate_status(data.get("status", "pending"))
        reference = _optional_text(data.get("reference"), "reference")
        notes = _optional_text(data.get("notes"), "notes")
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

    payment = Payment(
        business=g.current_business,
        customer_id=customer.id,
        conversation=conversation,
        amount=amount,
        currency=currency,
        reference=reference,
        method=method,
        status=status,
        notes=notes,
    )
    if status == "paid":
        payment.confirmed_by_user = g.current_user
        payment.confirmed_at = datetime.utcnow()
    commit()
    return jsonify({"payment": payment.to_dict()}), 201


@payments_bp.patch("/<int:payment_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_PAYMENTS)
@db_session
def update_payment(payment_id: int):
    payment = _payment_for_current_business(payment_id)
    if payment is None:
        return jsonify({"error": "Payment not found"}), 404

    data = _json_body()
    customer_id = payment.customer_id
    conversation = payment.conversation

    try:
        if "customer_id" in data:
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

        if "amount" in data:
            payment.amount = _parse_amount(data.get("amount"))
        if "currency" in data:
            payment.currency = _validate_currency(data.get("currency"))
        if "reference" in data:
            payment.reference = _optional_text(data.get("reference"), "reference")
        if "method" in data:
            payment.method = _validate_method(data.get("method"))
        if "status" in data:
            _set_status(payment, _validate_status(data.get("status")))
        if "notes" in data:
            payment.notes = _optional_text(data.get("notes"), "notes")
    except ValueError as exc:
        return _validation_error(str(exc))

    payment.customer_id = customer_id
    payment.conversation = conversation
    commit()
    return jsonify({"payment": payment.to_dict()}), 200


@payments_bp.post("/<int:payment_id>/mark-paid")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_PAYMENTS)
@db_session
def mark_payment_paid(payment_id: int):
    payment = _payment_for_current_business(payment_id)
    if payment is None:
        return jsonify({"error": "Payment not found"}), 404

    if payment.status != "paid":
        payment.status = "paid"
        payment.confirmed_by_user = g.current_user
        payment.confirmed_at = datetime.utcnow()
        commit()

    return jsonify({"payment": payment.to_dict()}), 200


@payments_bp.post("/<int:payment_id>/send-reminder")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_PAYMENTS)
@db_session
def send_payment_reminder(payment_id: int):
    payment = _payment_for_current_business(payment_id)
    if payment is None:
        return jsonify({"error": "Payment not found"}), 404

    conversation = _reminder_conversation(payment)
    if conversation is None:
        return _validation_error("A WhatsApp conversation is required to send a reminder")

    customer = _customer_for_current_business(payment.customer_id)
    recipient = (
        conversation.contact_phone_number
        or (customer.phone_number if customer is not None else None)
        or ""
    ).strip()
    if not recipient:
        return _validation_error("Customer WhatsApp phone number is required")

    reference_text = f" Reference: {payment.reference}." if payment.reference else ""
    body = (
        f"Payment reminder: {payment.currency} {format(payment.amount, 'f')} is pending."
        f"{reference_text}"
    )

    message = Message(
        business=g.current_business,
        conversation=conversation,
        customer_id=payment.customer_id,
        direction="outgoing",
        channel="whatsapp",
        message_type="text",
        body=body,
        status="pending",
        sent_by_user=g.current_user,
    )
    conversation.last_message_at = message.created_at
    conversation.updated_at = datetime.utcnow()
    commit()

    try:
        message.provider_message_id = send_whatsapp_message(message, recipient)
        message.status = "sent"
        commit()
    except WhatsAppSendError:
        message.status = "failed"
        commit()
        return jsonify({"message": message.to_dict(), "error": "Message send failed"}), 502

    return jsonify({"payment": payment.to_dict(), "message": message.to_dict()}), 201