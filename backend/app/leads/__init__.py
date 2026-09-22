from flask import Blueprint

leads_bp = Blueprint("leads", __name__, url_prefix="/api/leads")

from app.leads import models as _models  # noqa: F401,E402
