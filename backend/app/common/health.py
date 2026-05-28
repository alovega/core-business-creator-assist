from flask import Blueprint, jsonify
from pony.orm import db_session

from app import extensions
from app.db import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
    }
    status = "healthy" if all(item["status"] == "up" for item in checks.values()) else "unhealthy"
    code = 200 if status == "healthy" else 503
    return jsonify({"status": status, "checks": checks}), code


@db_session
def _check_database() -> dict:
    try:
        if db.provider is None:
            return {"status": "down", "error": "Database not initialized"}
        db.execute("SELECT 1")
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "error": str(exc)}


def _check_redis() -> dict:
    redis_client = extensions.redis_client
    if redis_client is None:
        return {"status": "down", "error": "Redis client not initialized"}
    try:
        redis_client.ping()
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "error": str(exc)}
