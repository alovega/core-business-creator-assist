from flask import Blueprint

conversations_bp = Blueprint("conversations", __name__, url_prefix="/api/conversations")
