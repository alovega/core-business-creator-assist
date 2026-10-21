from flask import g, jsonify
from pony.orm import db_session

from app.ai.providers import AIProviderError
from app.ai.services import AIConversationNotFound, AIReplyContextError, AIReplyService
from app.common.logging import get_logger
from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.conversations import conversations_bp

logger = get_logger(__name__)


@conversations_bp.post("/<int:conversation_id>/ai/suggest-reply")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def suggest_ai_reply(conversation_id: int):
    try:
        suggestion = AIReplyService.generate_reply(conversation_id=conversation_id, business_id=g.current_business.id)

    except AIConversationNotFound:
        return jsonify({"error": "Conversation not found"}), 404

    except AIReplyContextError:
        return jsonify(
            {"error": ("Conversation has no messages to reply to")}), 422

    except AIProviderError as exc:
        logger.warning("ai_reply_provider_failed", business_id=g.current_business.id, conversation_id=conversation_id, error_type=type(exc).__name__,)

        return jsonify({"error": ("AI reply suggestion is temporarily unavailable. Please write the reply manually.")}), 503

    return jsonify(
        {"conversation_id": conversation_id, "suggestion": suggestion, "auto_sent": False, "editable": True,}), 200