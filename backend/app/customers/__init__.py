from flask import Blueprint

customers_bp = Blueprint("customers", __name__, url_prefix="/api/customers")
