from flask import Blueprint

messages_bp = Blueprint("messages", __name__, url_prefix="/api/messages")
