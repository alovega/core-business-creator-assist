"""Cross-business access helpers and structured API errors."""

from flask import jsonify

from app.common.rbac.permissions import OWNER_ONLY_SETTING_KEYS


class ErrorCode:
    AUTH_REQUIRED = "AUTH_REQUIRED"
    BUSINESS_REQUIRED = "BUSINESS_REQUIRED"
    MEMBERSHIP_REQUIRED = "MEMBERSHIP_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    ROLE_REQUIRED = "ROLE_REQUIRED"


def api_error(code: str, message: str, status: int):
    return jsonify({"error": code, "message": message}), status


def auth_required(message: str = "Authentication required"):
    return api_error(ErrorCode.AUTH_REQUIRED, message, 401)


def business_required_error(message: str = "No business workspace"):
    return api_error(ErrorCode.BUSINESS_REQUIRED, message, 404)


def membership_required(message: str = "Active business membership required"):
    return api_error(ErrorCode.MEMBERSHIP_REQUIRED, message, 403)


def permission_denied(
    message: str | None = None,
    *,
    permission: str | None = None,
):
    if message is None and permission is not None:
        message = f"Missing permission: {permission}"
    if message is None:
        message = "Permission denied"
    return api_error(ErrorCode.PERMISSION_DENIED, message, 403)


def role_required_error(message: str):
    return api_error(ErrorCode.ROLE_REQUIRED, message, 403)


def forbidden(message: str = "Permission denied"):
    """Backward-compatible helper; prefer permission_denied with ErrorCode."""
    return permission_denied(message)


def owner_only_setting_keys(settings: dict) -> set[str]:
    return set(settings.keys()) & OWNER_ONLY_SETTING_KEYS
