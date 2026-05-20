from flask import current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.auth import auth_bp
from app.auth.services import (
    MIN_PASSWORD_LENGTH,
    blacklist_token,
    consume_password_reset_token,
    create_access_token,
    create_password_reset_token,
    get_token_remaining_seconds,
    hash_password,
    verify_password,
)
from app.common.auth import require_auth
from app.extensions import db
from app.users.models import User


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


@auth_bp.post("/register")
def register():
    data = _json_body()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip() or "user"
    business_id = data.get("business_id")

    if not name:
        return _validation_error("Name is required")
    if not email:
        return _validation_error("Email is required")
    if len(password) < MIN_PASSWORD_LENGTH:
        return _validation_error(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        business_id=business_id,
        is_active=True,
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Email already registered"}), 409

    token, _ = create_access_token(
        user.id,
        current_app.config["JWT_SECRET"],
        current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
    )
    return jsonify({"user": user.to_dict(), "access_token": token}), 201


@auth_bp.post("/login")
def login():
    data = _json_body()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Invalid credentials"}), 401

    user = User.query.filter_by(email=email).first()
    if user is None or not verify_password(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.is_active:
        return jsonify({"error": "Account inactive"}), 403

    token, _ = create_access_token(
        user.id,
        current_app.config["JWT_SECRET"],
        current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
    )
    return jsonify({"user": user.to_dict(), "access_token": token}), 200


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
def me():
    return jsonify({"user": g.current_user.to_dict()}), 200


@auth_bp.post("/forgot-password")
def forgot_password():
    data = _json_body()
    email = (data.get("email") or "").strip().lower()

    if email:
        user = User.query.filter_by(email=email, is_active=True).first()
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
def reset_password():
    data = _json_body()
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""

    if not token:
        return _validation_error("Reset token is required")
    if len(password) < MIN_PASSWORD_LENGTH:
        return _validation_error(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    user_id = consume_password_reset_token(token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user.password_hash = hash_password(password)
    db.session.commit()
    return jsonify({"message": "Password reset successfully"}), 200
