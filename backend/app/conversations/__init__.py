from flask import Blueprint

conversations_bp = Blueprint("conversations", __name__, url_prefix="/api/conversations")

from app.conversations import models as _models  # noqa: F401,E402
