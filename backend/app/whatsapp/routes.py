from __future__ import annotations

from flask import current_app, g, jsonify, request
from pony.orm import commit, db_session

from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.whatsapp import whatsapp_bp
from app.whatsapp.client import WhatsAppApiError, WhatsAppClient
from app.whatsapp.models import WhatsAppIntegration
from app.whatsapp.services import (
    create_or_update_integration,
    decrypt_secret,
    disconnect_integration,
    get_integration_for_business,
)
from app.whatsapp.validators import (
    serialize_integration,
    serialize_outbound_result,
    validate_integration_payload,
    validate_send_message_payload,
    validate_test_message_payload,
)


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


@whatsapp_bp.get("/integration")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_WHATSAPP)
@db_session
def get_integration():
    integration = get_integration_for_business(g.current_business)
    if integration is None:
        return jsonify({"integration": None}), 200
    return jsonify({"integration": serialize_integration(integration)}), 200


@whatsapp_bp.post("/integration")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_WHATSAPP)
@db_session
def create_integration():
    data = _json_body()
    errors = validate_integration_payload(data)
    if errors:
        return jsonify({"error": "Invalid payload", "errors": errors}), 400
    integration, _ = create_or_update_integration(
        business=g.current_business,
        actor=g.current_user,
        data=data,
    )
    commit()
    return jsonify({"integration": serialize_integration(integration)}), 201


@whatsapp_bp.patch("/integration")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_WHATSAPP)
@db_session
def patch_integration():
    data = _json_body()
    errors = validate_integration_payload(data, partial=True)
    if errors:
        return jsonify({"error": "Invalid payload", "errors": errors}), 400
    phone_number_id = data.get("phone_number_id")
    if not isinstance(phone_number_id, str) or not phone_number_id.strip():
        return jsonify({"error": "phone_number_id is required"}), 400
    integration = WhatsAppIntegration.get(
        business=g.current_business,
        phone_number_id=phone_number_id.strip(),
    )
    if integration is None:
        return jsonify({"error": "Integration not found"}), 404
    data.setdefault(
        "whatsapp_business_account_id",
        integration.whatsapp_business_account_id or "",
    )
    data.setdefault("display_phone_number", integration.display_phone_number or "")
    integration, _ = create_or_update_integration(
        business=g.current_business,
        actor=g.current_user,
        data=data,
    )
    commit()
    return jsonify({"integration": serialize_integration(integration)}), 200


@whatsapp_bp.delete("/integration")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_WHATSAPP)
@db_session
def delete_integration():
    phone_number_id = (request.args.get("phone_number_id") or "").strip()
    integration = get_integration_for_business(
        g.current_business,
        phone_number_id=phone_number_id or None,
    )
    if integration is None:
        return jsonify({"error": "Integration not found"}), 404
    disconnect_integration(integration=integration, actor=g.current_user)
    commit()
    return jsonify({"message": "WhatsApp disconnected"}), 200


def _send_message_to_whatsapp(*, integration, to: str, body: str) -> dict:
    client = WhatsAppClient(
        phone_number_id=integration.phone_number_id,
        access_token=decrypt_secret(integration.access_token_encrypted),
        api_version=current_app.config.get("WHATSAPP_API_VERSION", "v21.0"),
    )
    return client.send_text_message(to=to, body=body)


@whatsapp_bp.post("/send-message")
@login_required
@business_required
@permission_required(PermissionKey.SEND_WHATSAPP_MESSAGES)
@db_session
def send_message():
    data = _json_body()
    errors = validate_send_message_payload(data)
    if errors:
        return jsonify({"error": "Invalid payload", "errors": errors}), 400
    integration = get_integration_for_business(
        g.current_business,
        phone_number_id=(data.get("phone_number_id") or "").strip() or None,
    )
    if integration is None:
        return jsonify({"error": "No active WhatsApp integration for this business"}), 409
    try:
        response = _send_message_to_whatsapp(
            integration=integration,
            to=data["phone_number"].strip(),
            body=data["body"].strip(),
        )
    except WhatsAppApiError as exc:
        return (
            jsonify(
                {
                    "error": str(exc),
                    "provider_error": exc.details,
                }
            ),
            exc.status_code or 502,
        )
    return jsonify({"result": serialize_outbound_result(response)}), 200


@whatsapp_bp.post("/test-message")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_WHATSAPP)
@db_session
def send_test_message():
    data = _json_body()
    errors = validate_test_message_payload(data)
    if errors:
        return jsonify({"error": "Invalid payload", "errors": errors}), 400
    integration = get_integration_for_business(
        g.current_business,
        phone_number_id=(data.get("phone_number_id") or "").strip() or None,
    )
    if integration is None:
        return jsonify({"error": "No active WhatsApp integration for this business"}), 409
    body = (data.get("body") or "Test message from Business Creator Assist").strip()
    try:
        response = WhatsAppClient(
            phone_number_id=integration.phone_number_id,
            access_token=decrypt_secret(integration.access_token_encrypted),
            api_version=current_app.config.get("WHATSAPP_API_VERSION", "v21.0"),
        ).send_test_message(
            to=data["phone_number"].strip(),
            body=body,
        )
    except WhatsAppApiError as exc:
        return (
            jsonify(
                {
                    "error": str(exc),
                    "provider_error": exc.details,
                }
            ),
            exc.status_code or 502,
        )
    return jsonify({"result": serialize_outbound_result(response)}), 200
