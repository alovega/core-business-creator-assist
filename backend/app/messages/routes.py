from datetime import datetime, timezone

from flask import g, jsonify, request
from pony.orm import commit, db_session, select

from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.conversations import conversations_bp
from app.conversations.models import Conversation
from app.messages import messages_bp
from app.messages.models import Message
from app.messages.services import WhatsAppSendError, send_whatsapp_message

SUPPORTED_MESSAGE_TYPES = frozenset({"text", "image", "video", "audio", "document"})


def _parse_since():
    raw = request.args.get("since")
    if not raw:
        return datetime.min
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _poll_cursor() -> str:
    return datetime.utcnow().isoformat(timespec="microseconds") + "Z"


def _invalid_since():
    return jsonify({"error": "since must be an ISO-8601 timestamp"}), 400


def _conversation_payload(conversation: Conversation) -> dict:
    payload = conversation.to_dict()
    payload["unread_count"] = sum(
        1 for message in conversation.messages if message.direction == "incoming"
    )
    return payload


@conversations_bp.get("/updates")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def conversation_updates():
    since = _parse_since()
    if since is None:
        return _invalid_since()

    conversations = list(
        select(
            conversation
            for conversation in Conversation
            if conversation.business == g.current_business
            and conversation.updated_at > since
        ).order_by(lambda conversation: conversation.updated_at)
    )
    return jsonify(
        {
            "conversations": [_conversation_payload(item) for item in conversations],
            "since": _poll_cursor(),
        }
    ), 200


@conversations_bp.get("/<int:conversation_id>/messages/updates")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def message_updates(conversation_id: int):
    since = _parse_since()
    if since is None:
        return _invalid_since()

    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404

    messages = list(
        select(
            message
            for message in Message
            if message.conversation == conversation and message.created_at > since
        ).order_by(lambda message: message.created_at)
    )
    return jsonify(
        {"messages": [item.to_dict() for item in messages], "since": _poll_cursor()}
    ), 200


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


def _conversation_for_current_business(conversation_id: int) -> Conversation | None:
    return Conversation.get(id=conversation_id, business=g.current_business)


@messages_bp.get("/<int:conversation_id>")
@messages_bp.post("/<int:conversation_id>")
@conversations_bp.get("/<int:conversation_id>/messages")
@conversations_bp.post("/<int:conversation_id>/messages")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def conversation_messages(conversation_id: int):
    conversation = _conversation_for_current_business(conversation_id)
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404

    if request.method == "GET":
        messages = sorted(
            list(conversation.messages), key=lambda message: message.created_at
        )
        return jsonify({"messages": [message.to_dict() for message in messages]}), 200

    data = _json_body()
    channel = (data.get("channel") or conversation.channel or "whatsapp").strip().lower()
    message_type = (data.get("message_type") or "text").strip().lower()
    body = data.get("body")
    media_url = data.get("media_url")
    recipient = (data.get("to") or conversation.contact_phone_number or "").strip()

    if channel != "whatsapp":
        return _validation_error("Only WhatsApp messages are supported")
    if message_type not in SUPPORTED_MESSAGE_TYPES:
        return _validation_error("Unsupported message_type")
    if message_type == "text" and not isinstance(body, str):
        return _validation_error("body is required for text messages")
    if message_type != "text" and not isinstance(media_url, str):
        return _validation_error("media_url is required for media messages")
    if not recipient:
        return _validation_error("WhatsApp recipient is required")

    message_data = dict(
        business=g.current_business,
        conversation=conversation,
        customer_id=conversation.customer_id,
        direction="outgoing",
        channel=channel,
        message_type=message_type,
        status="pending",
        sent_by_user=g.current_user,
    )
    if isinstance(body, str):
        message_data["body"] = body.strip()
    if isinstance(media_url, str):
        message_data["media_url"] = media_url.strip()
    message = Message(**message_data)
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

    return jsonify({"message": message.to_dict()}), 201
