from __future__ import annotations

from app.common.time import utc_now_naive


def validate_integration_payload(data: dict, *, partial: bool = False) -> dict[str, str]:
    required = (
        "phone_number_id",
        "whatsapp_business_account_id",
        "display_phone_number",
        "access_token",
        "verify_token",
        "app_secret",
    )
    errors: dict[str, str] = {}
    for field in required:
        if partial and field not in data:
            continue
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors[field] = f"{field} is required"
    return errors


def validate_send_message_payload(data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    for field in ("phone_number", "body"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors[field] = f"{field} is required"
    phone_number_id = data.get("phone_number_id")
    if phone_number_id is not None and (
        not isinstance(phone_number_id, str) or not phone_number_id.strip()
    ):
        errors["phone_number_id"] = "phone_number_id must be a non-empty string"
    return errors


def validate_test_message_payload(data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    phone_number = data.get("phone_number")
    if not isinstance(phone_number, str) or not phone_number.strip():
        errors["phone_number"] = "phone_number is required"
    body = data.get("body")
    if body is not None and (not isinstance(body, str) or not body.strip()):
        errors["body"] = "body must be a non-empty string"
    phone_number_id = data.get("phone_number_id")
    if phone_number_id is not None and (
        not isinstance(phone_number_id, str) or not phone_number_id.strip()
    ):
        errors["phone_number_id"] = "phone_number_id must be a non-empty string"
    return errors


def serialize_integration(integration) -> dict:
    return {
        "id": integration.id,
        "business_id": integration.business.id,
        "phone_number_id": integration.phone_number_id,
        "whatsapp_business_account_id": integration.whatsapp_business_account_id,
        "display_phone_number": integration.display_phone_number,
        "status": integration.status,
        "connected_at": integration.connected_at.isoformat() + "Z"
        if integration.connected_at
        else None,
        "disconnected_at": integration.disconnected_at.isoformat() + "Z"
        if integration.disconnected_at
        else None,
        "created_by_id": integration.created_by.id if integration.created_by else None,
        "updated_by_id": integration.updated_by.id if integration.updated_by else None,
        "created_at": integration.created_at.isoformat() + "Z",
        "updated_at": integration.updated_at.isoformat() + "Z",
    }


def serialize_outbound_result(result: dict) -> dict:
    return {
        "ok": bool(result.get("ok")),
        "provider": result.get("provider"),
        "provider_message_id": result.get("provider_message_id"),
        "recipient_wa_id": result.get("recipient_wa_id"),
    }


def now():
    return utc_now_naive()
