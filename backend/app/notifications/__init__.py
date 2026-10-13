from flask import Blueprint

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")

from app.notifications import models as _models  # noqa: F401,E402