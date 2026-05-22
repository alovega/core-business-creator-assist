import secrets
from datetime import datetime, timedelta, timezone

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from app import extensions

PASSWORD_RESET_PREFIX = "password_reset:"
TOKEN_BLACKLIST_PREFIX = "jwt_blacklist:"
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def create_access_token(user_id: int, jwt_secret: str, expires_seconds: int) -> tuple[str, str]:
    jti = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=expires_seconds)
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "exp": expires,
        "iat": now,
        "type": "access",
    }
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")
    return token, jti


def decode_access_token(token: str, jwt_secret: str) -> dict:
    return jwt.decode(token, jwt_secret, algorithms=["HS256"])


def get_token_remaining_seconds(payload: dict, default_seconds: int) -> int:
    exp = payload.get("exp")
    if exp is None:
        return default_seconds
    remaining = int(exp - datetime.now(timezone.utc).timestamp())
    return max(remaining, 1)


def is_token_blacklisted(jti: str) -> bool:
    redis = extensions.redis_client
    if redis is None:
        return False
    return redis.exists(f"{TOKEN_BLACKLIST_PREFIX}{jti}") > 0


def blacklist_token(jti: str, expires_in: int) -> None:
    redis = extensions.redis_client
    if redis is None:
        return
    redis.setex(f"{TOKEN_BLACKLIST_PREFIX}{jti}", expires_in, "1")


def create_password_reset_token(user_id: int, expires_seconds: int) -> str:
    token = secrets.token_urlsafe(32)
    redis = extensions.redis_client
    if redis is None:
        raise RuntimeError("Redis client not initialized")
    redis.setex(f"{PASSWORD_RESET_PREFIX}{token}", expires_seconds, str(user_id))
    return token


def consume_password_reset_token(token: str) -> int | None:
    redis = extensions.redis_client
    if redis is None:
        return None
    key = f"{PASSWORD_RESET_PREFIX}{token}"
    user_id = redis.get(key)
    if user_id is None:
        return None
    redis.delete(key)
    return int(user_id)
