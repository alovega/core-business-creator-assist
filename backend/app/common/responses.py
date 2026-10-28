"""Shared API responses and non-breaking normalization of legacy JSON routes.

Contract: success, message, data, error, code, details. Existing top-level
payload fields are retained during migration so current consumers still work.
"""

from flask import jsonify, request

_STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_SERVER_ERROR",
    503: "SERVICE_UNAVAILABLE",
}
_DEFAULT_MESSAGES = {
    400: "Invalid request",
    401: "Authentication required",
    403: "Permission denied",
    404: "Resource not found",
    405: "Method not allowed",
    409: "Resource conflict",
    500: "Internal server error",
    503: "Service unavailable",
}
_RESERVED = {"success", "message", "data", "error", "code", "details"}


def success_response(data=None, message="Success", status=200):
    """Return a standard success payload; data may be any JSON-serializable value."""
    return jsonify(success=True, message=message, data=data, error=None, code=None, details=None), status


def error_response(message, status=400, *, code=None, details=None):
    """Return standard error JSON with optional field-level validation details."""
    return jsonify(
        success=False, message=message, data=None, error=message,
        code=code or _STATUS_CODES.get(status, "REQUEST_ERROR"), details=details,
    ), status


def validation_error(details, message="Please correct the errors below."):
    return error_response(message, 400, code="VALIDATION_ERROR", details=details)


def auth_error(message="Authentication required"):
    return error_response(message, 401, code="AUTH_REQUIRED")


def forbidden_error(message="Permission denied"):
    return error_response(message, 403, code="FORBIDDEN")


def not_found_error(message="Resource not found"):
    return error_response(message, 404, code="NOT_FOUND")


def server_error():
    return error_response("Internal server error", 500, code="INTERNAL_SERVER_ERROR")


def standardize_api_responses(app):
    """Normalize legacy /api JSON without rewriting every existing endpoint.

    Leaves 204/304, streaming, binary, and non-API responses untouched.
    Legacy fields (including `error` and `errors`) remain accessible.
    """

    @app.after_request
    def standardize(response):
        # OpenAPI is itself a JSON document, not an application API payload.
        # Wrapping it in the usual success envelope breaks Swagger UI imports.
        if request.path == "/api/openapi.json":
            return response
        if not (request.path == "/api" or request.path.startswith("/api/")):
            return response
        if response.status_code in (204, 304) or not response.is_json:
            return response
        payload = response.get_json(silent=True)
        if payload is None:
            return response
        status = response.status_code
        if isinstance(payload, dict) and "success" in payload and "data" in payload:
            return response  # Already using shared helpers.

        if status >= 400:
            original = payload if isinstance(payload, dict) else {}
            old_error = original.get("error")
            message = original.get("message") or (
                old_error if isinstance(old_error, str) else None
            ) or _DEFAULT_MESSAGES.get(status, "Request failed")
            # Some legacy RBAC errors use `error` as a machine-readable code.
            machine_code = old_error if isinstance(old_error, str) and old_error in {
                "AUTH_REQUIRED", "BUSINESS_REQUIRED", "MEMBERSHIP_REQUIRED",
                "PERMISSION_DENIED", "ROLE_REQUIRED",
            } else _STATUS_CODES.get(status, "REQUEST_ERROR")
            details = original.get("details", original.get("errors"))
            result = {
                **original, "success": False, "data": None,
                "message": message, "code": machine_code, "details": details,
                "error": old_error if isinstance(old_error, str) else message,
            }
        else:
            original = payload if isinstance(payload, dict) else {}
            result = {
                **original, "success": True,
                "message": original.get("message") or "Success",
                "data": payload, "error": None, "code": None, "details": None,
            }
        response.set_data(app.json.dumps(result) + "\n")
        response.mimetype = "application/json"
        return response