from functools import wraps

from flask import g, jsonify

from app.businesses.models import Business
from app.extensions import db


def current_business_id() -> int | None:
    return getattr(g, "business_id", None)


def require_business(view):
    """Require an authenticated user with an assigned business workspace."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user.business_id is None:
            return jsonify({"error": "No business workspace"}), 404

        business = db.session.get(Business, g.current_user.business_id)
        if business is None:
            return jsonify({"error": "No business workspace"}), 404

        g.business_id = business.id
        g.current_business = business
        return view(*args, **kwargs)

    return wrapped
