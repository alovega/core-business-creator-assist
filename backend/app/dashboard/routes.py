from flask import g, jsonify, request
from pony.orm import db_session

from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.dashboard import dashboard_bp
from app.dashboard.services import (
    booking_metrics,
    conversation_metrics,
    lead_metrics,
    parse_date_range,
    payment_metrics,
    summary_metrics,
)


def _date_range_or_error():
    try:
        return parse_date_range(
            request.args.get("start_date"),
            request.args.get("end_date"),
        ), None
    except ValueError as exc:
        return None, (jsonify({"error": str(exc)}), 400)


def _dashboard_response(metric_builder):
    date_range, error = _date_range_or_error()
    if error is not None:
        return error

    return jsonify(
        {
            "business_id": g.current_business.id,
            "date_range": date_range.to_dict(),
            "metrics": metric_builder(g.current_business, date_range),
        }
    ), 200


@dashboard_bp.get("/summary")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_DASHBOARD)
@db_session
def dashboard_summary():
    return _dashboard_response(summary_metrics)


@dashboard_bp.get("/conversations")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_DASHBOARD)
@db_session
def dashboard_conversations():
    return _dashboard_response(conversation_metrics)


@dashboard_bp.get("/leads")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_DASHBOARD)
@db_session
def dashboard_leads():
    return _dashboard_response(lead_metrics)


@dashboard_bp.get("/bookings")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_DASHBOARD)
@db_session
def dashboard_bookings():
    return _dashboard_response(booking_metrics)


@dashboard_bp.get("/payments")
@login_required
@business_required
@permission_required(PermissionKey.VIEW_DASHBOARD)
@db_session
def dashboard_payments():
    return _dashboard_response(payment_metrics)
