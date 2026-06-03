from flask import g, jsonify, request
from pony.orm import commit, db_session

from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.conversations import conversations_bp
from app.conversations.services import (
    assign_conversation,
    get_conversation_for_business,
    list_conversations,
    mark_read,
    unassign_conversation,
    update_conversation,
)
from app.conversations.validators import (
    parse_list_filters,
    serialize_conversation,
    validate_patch_payload,
)


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_errors(errors: dict[str, str]):
    if len(errors) == 1:
        message = next(iter(errors.values()))
    else:
        message = "Please correct the errors below."
    return jsonify({"error": message, "errors": errors}), 400


@conversations_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CONVERSATIONS)
@db_session
def list_conversations_route():
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", 20, type=int) or 20
    filters, errors = parse_list_filters(request.args)
    if errors:
        return _validation_errors(errors)
    conversations, total = list_conversations(
        business=g.current_business,
        filters=filters,
        page=page,
        per_page=per_page,
    )
    return (
        jsonify(
            {
                "conversations": [serialize_conversation(c) for c in conversations],
                "page": page,
                "per_page": per_page,
                "total": total,
            }
        ),
        200,
    )


@conversations_bp.get("/<int:conversation_id>")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_CONVERSATIONS)
@db_session
def get_conversation_route(conversation_id: int):
    conversation = get_conversation_for_business(
        business=g.current_business,
        conversation_id=conversation_id,
    )
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"conversation": serialize_conversation(conversation)}), 200


@conversations_bp.patch("/<int:conversation_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def patch_conversation_route(conversation_id: int):
    conversation = get_conversation_for_business(
        business=g.current_business,
        conversation_id=conversation_id,
    )
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    payload = _json_body()
    errors = validate_patch_payload(payload)
    if errors:
        return _validation_errors(errors)
    updated = update_conversation(
        conversation=conversation,
        actor=g.current_user,
        updates=payload,
    )
    commit()
    return jsonify({"conversation": serialize_conversation(updated)}), 200


@conversations_bp.post("/<int:conversation_id>/assign")
@login_required
@business_required
@permission_required(PermissionKey.ASSIGN_CONVERSATIONS)
@db_session
def assign_conversation_route(conversation_id: int):
    conversation = get_conversation_for_business(
        business=g.current_business,
        conversation_id=conversation_id,
    )
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    payload = _json_body()
    membership_id = payload.get("membership_id")
    user_id = payload.get("user_id")
    try:
        updated = assign_conversation(
            conversation=conversation,
            business=g.current_business,
            actor=g.current_user,
            membership_id=int(membership_id) if membership_id is not None else None,
            user_id=int(user_id) if user_id is not None else None,
        )
        commit()
        return jsonify({"conversation": serialize_conversation(updated)}), 200
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@conversations_bp.post("/<int:conversation_id>/unassign")
@login_required
@business_required
@permission_required(PermissionKey.ASSIGN_CONVERSATIONS)
@db_session
def unassign_conversation_route(conversation_id: int):
    conversation = get_conversation_for_business(
        business=g.current_business,
        conversation_id=conversation_id,
    )
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    updated = unassign_conversation(conversation=conversation, actor=g.current_user)
    commit()
    return jsonify({"conversation": serialize_conversation(updated)}), 200


@conversations_bp.post("/<int:conversation_id>/mark-read")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def mark_read_route(conversation_id: int):
    conversation = get_conversation_for_business(
        business=g.current_business,
        conversation_id=conversation_id,
    )
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    updated = mark_read(conversation=conversation, actor=g.current_user)
    commit()
    return jsonify({"conversation": serialize_conversation(updated)}), 200


@conversations_bp.post("/<int:conversation_id>/archive")
@login_required
@business_required
@permission_required(PermissionKey.CLOSE_CONVERSATIONS)
@db_session
def archive_conversation_route(conversation_id: int):
    conversation = get_conversation_for_business(
        business=g.current_business,
        conversation_id=conversation_id,
    )
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    updated = update_conversation(
        conversation=conversation,
        actor=g.current_user,
        updates={"status": "archived"},
    )
    commit()
    return jsonify({"conversation": serialize_conversation(updated)}), 200


@conversations_bp.post("/<int:conversation_id>/close")
@login_required
@business_required
@permission_required(PermissionKey.CLOSE_CONVERSATIONS)
@db_session
def close_conversation_route(conversation_id: int):
    conversation = get_conversation_for_business(
        business=g.current_business,
        conversation_id=conversation_id,
    )
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    updated = update_conversation(
        conversation=conversation,
        actor=g.current_user,
        updates={"status": "closed"},
    )
    commit()
    return jsonify({"conversation": serialize_conversation(updated)}), 200


@conversations_bp.post("/<int:conversation_id>/reopen")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def reopen_conversation_route(conversation_id: int):
    conversation = get_conversation_for_business(
        business=g.current_business,
        conversation_id=conversation_id,
    )
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    updated = update_conversation(
        conversation=conversation,
        actor=g.current_user,
        updates={"status": "open"},
    )
    commit()
    return jsonify({"conversation": serialize_conversation(updated)}), 200
