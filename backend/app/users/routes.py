from flask import g, jsonify

from app.businesses.membership_service import list_business_members
from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.users import users_bp
from app.users.models import User


@users_bp.get("")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_MEMBERS)
def list_users():
    members = list_business_members(g.current_business)
    users = [
        {
            **m.user.to_dict(),
            "role": m.role.key,
            "membership_status": m.status,
            "membership_user_id": m.user.id,
            "membership_business_id": m.business.id,
        }
        for m in members
        if m.status != "removed"
    ]
    return jsonify({"users": users}), 200


@users_bp.get("/<int:user_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_MEMBERS)
def get_user(user_id: int):
    from app.businesses.models import BusinessMembership

    user = User.get(id=user_id)
    target_membership = BusinessMembership.get(
        user=user,
        business=g.current_business,
    )
    if (
        user is None
        or target_membership is None
        or target_membership.status == "removed"
    ):
        return jsonify({"error": "User not found"}), 404

    payload = user.to_dict()
    payload["role"] = target_membership.role.key
    payload["membership_status"] = target_membership.status
    payload["membership_user_id"] = target_membership.user.id
    payload["membership_business_id"] = target_membership.business.id
    return jsonify({"user": payload}), 200
