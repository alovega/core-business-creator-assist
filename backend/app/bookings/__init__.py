from flask import Blueprint

bookings_bp = Blueprint("bookings", __name__, url_prefix="/api/bookings")
