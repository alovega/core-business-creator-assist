from flask import current_app, g, jsonify, request
from pony.orm import commit, db_session

from app.auth import auth_bp
from app.auth.services import (
    blacklist_token,
    consume_password_reset_token,
    create_access_token,
    create_password_reset_token,
    get_token_remaining_seconds,
    hash_password,
    verify_password,
)
from app.auth.validators import (
    login_identifier_from_body,
    validate_login_fields,
    validate_register_fields,
    validate_reset_password_fields,
)
from app.businesses.membership_service import list_accessible_businesses
from app.common.auth import require_auth
from app.common.db_errors import is_unique_violation
from app.common.tenant import ensure_default_current_business
from app.users.models import User


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


def _validation_errors(field_errors: dict[str, str]):
    if len(field_errors) == 1:
        message = next(iter(field_errors.values()))
    else:
        message = "Please correct the errors below."
    return jsonify({"error": message, "errors": field_errors}), 400


@auth_bp.post("/register")
@db_session
def register():
    data = _json_body()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    register_errors = validate_register_fields(name, email, password)
    if register_errors:
        return _validation_errors(register_errors)

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        is_active=True,
    )
    try:
        commit()
    except Exception as exc:
        if is_unique_violation(exc):
            return jsonify({"error": "Email already registered"}), 409
        raise

    ensure_default_current_business(user)
    commit()

    token, _ = create_access_token(
        user.id,
        current_app.config["JWT_SECRET"],
        current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        business_id=user.current_business_id,
    )
    return jsonify(
        {
            "user": user.to_dict(),
            "access_token": token,
            "businesses": list_accessible_businesses(user),
        }
    ), 201


@auth_bp.post("/login")
@db_session
def login():
    data = _json_body()
    email = login_identifier_from_body(data)
    password = data.get("password") or ""

    login_errors = validate_login_fields(email, password)
    if login_errors:
        return _validation_errors(login_errors)

    user = User.get(email=email)
    if user is None or not verify_password(user.password_hash, password):
        return jsonify(
            {
                "error": (
                    "Invalid email or password. "
                    "Please check your credentials and try again."
                )
            }
        ), 401

    if not user.is_active:
        return jsonify({"error": "Account inactive"}), 403

    ensure_default_current_business(user)
    commit()

    token, _ = create_access_token(
        user.id,
        current_app.config["JWT_SECRET"],
        current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        business_id=user.current_business_id,
    )
    return jsonify(
        {
            "user": user.to_dict(),
            "access_token": token,
            "businesses": list_accessible_businesses(user),
        }
    ), 200


@auth_bp.post("/logout")
@require_auth
def logout():
    payload = g.token_payload
    jti = payload.get("jti")
    if jti:
        remaining = get_token_remaining_seconds(
            payload,
            current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        )
        blacklist_token(jti, remaining)
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.get("/me")
@require_auth
@db_session
def me():
    ensure_default_current_business(g.current_user)
    commit()
    return jsonify(
        {
            "user": g.current_user.to_dict(),
            "businesses": list_accessible_businesses(g.current_user),
        }
    ), 200


@auth_bp.post("/forgot-password")
@db_session
def forgot_password():
    data = _json_body()
    email = (data.get("email") or "").strip().lower()

    if email:
        user = User.get(email=email, is_active=True)
        if user is not None:
            create_password_reset_token(
                user.id,
                current_app.config["PASSWORD_RESET_TOKEN_EXPIRES"],
            )

    return jsonify(
        {
            "message": (
                "If an account with that email exists, "
                "password reset instructions have been sent."
            )
        }
    ), 200


@auth_bp.post("/reset-password")
@db_session
def reset_password():
    data = _json_body()
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""

    if not token:
        return _validation_error("Reset token is required")

    reset_errors = validate_reset_password_fields(password)
    if reset_errors:
        return _validation_errors(reset_errors)

    user_id = consume_password_reset_token(token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user = User.get(id=user_id)
    if user is None or not user.is_active:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user.password_hash = hash_password(password)
    commit()
    return jsonify({"message": "Password reset successfully"}), 200
