from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from app.auth.services import decode_access_token, is_token_blacklisted
from app.extensions import db
from app.users.models import User


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401

        token = auth_header[len("Bearer ") :]
        try:
            payload = decode_access_token(token, current_app.config["JWT_SECRET"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        if payload.get("type") != "access":
            return jsonify({"error": "Invalid token"}), 401

        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            return jsonify({"error": "Token revoked"}), 401

        user = db.session.get(User, int(payload.get("sub")))
        if user is None:
            return jsonify({"error": "User not found"}), 401
        if not user.is_active:
            return jsonify({"error": "Account inactive"}), 403

        g.current_user = user
        g.token_payload = payload
        return view(*args, **kwargs)

    return wrapped
