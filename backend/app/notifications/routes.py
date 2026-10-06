from flask import g, jsonify, request
from pony.orm import commit, count, db_session, desc, select

from app.common.rbac.decorators import business_required, login_required
from app.notifications import notifications_bp
from app.notifications.models import Notification


def _read_filter():
    raw = request.args.get("is_read")
    if raw is None or raw == "":
        return None
    normalized = raw.strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValueError("is_read must be true or false")


def _notification_for_current_user(notification_id: int) -> Notification | None:
    return Notification.get(
        id=notification_id,
        business=g.current_business,
        user=g.current_user,
    )


@notifications_bp.get("")
@login_required
@business_required
@db_session
def list_notifications():
    try:
        is_read = _read_filter()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    notifications = list(
        select(
            notification
            for notification in Notification
            if notification.business == g.current_business
            and notification.user == g.current_user
            and (is_read is None or notification.is_read == is_read)
        ).order_by(lambda notification: desc(notification.created_at))
    )
    unread_count = count(
        notification
        for notification in Notification
        if notification.business == g.current_business
        and notification.user == g.current_user
        and not notification.is_read
    )
    return jsonify(
        {
            "notifications": [item.to_dict() for item in notifications],
            "unread_count": unread_count,
        }
    ), 200


@notifications_bp.post("/<int:notification_id>/read")
@login_required
@business_required
@db_session
def mark_notification_read(notification_id: int):
    notification = _notification_for_current_user(notification_id)
    if notification is None:
        return jsonify({"error": "Notification not found"}), 404

    if not notification.is_read:
        notification.is_read = True
        commit()

    return jsonify({"notification": notification.to_dict()}), 200