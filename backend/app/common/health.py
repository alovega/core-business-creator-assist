from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app import extensions
from app.extensions import db

health_bp = Blueprint("health", __name__)


def _check_database() -> dict:
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "up"}
    except Exception as exc:
        current_app.logger.exception("database_health_check_failed")
        return {"status": "down", "error": str(exc)}


def _check_redis() -> dict:
    try:
        if extensions.redis_client is None:
            raise RuntimeError("Redis client not initialized")
        extensions.redis_client.ping()
        return {"status": "up"}
    except Exception as exc:
        current_app.logger.exception("redis_health_check_failed")
        return {"status": "down", "error": str(exc)}


@health_bp.get("/health")
def health():
    database = _check_database()
    redis_health = _check_redis()
    checks = {"database": database, "redis": redis_health}
    healthy = all(check["status"] == "up" for check in checks.values())
    body = {
        "status": "healthy" if healthy else "unhealthy",
        "checks": checks,
    }
    status_code = 200 if healthy else 503
    return jsonify(body), status_code
