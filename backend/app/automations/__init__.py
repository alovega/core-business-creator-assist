from flask import Blueprint

automations_bp = Blueprint("automations", __name__, url_prefix="/api/automations")

from app.automations import models as _models  # noqa: F401,E402
