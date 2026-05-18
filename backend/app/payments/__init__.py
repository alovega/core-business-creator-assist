from flask import Blueprint

payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")
