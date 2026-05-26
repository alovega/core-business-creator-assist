"""HTTP and domain helpers reused across colocated module tests."""

from datetime import datetime

from pony.orm import commit, db_session

from app.businesses.membership_status import MembershipStatus
from app.businesses.models import Business, BusinessMembership
from app.common.rbac.roles import get_system_role
from app.users.models import User


def register_user(client, **overrides):
    payload = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "password": "securepass123",
    }
    payload.update(overrides)
    return client.post("/api/auth/register", json=payload)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_business(client, token, **overrides):
    payload = {
        "name": "Acme Corp",
        "phone_number": "+1234567890",
        "industry": "retail",
    }
    payload.update(overrides)
    return client.post(
        "/api/businesses",
        json=payload,
        headers=auth_headers(token),
    )


def add_business_member(
    app,
    email: str,
    business_id: int,
    *,
    role: str = "staff",
    status: str = MembershipStatus.ACTIVE.value,
    set_current: bool = True,
):
    with app.app_context():

        @db_session
        def _add():
            user = User.get(email=email)
            business = Business.get(id=business_id)
            role_entity = get_system_role(role)
            assert role_entity is not None
            membership = BusinessMembership.get(user=user, business=business)
            now = datetime.utcnow()
            if membership is None:
                membership = BusinessMembership(
                    user=user,
                    business=business,
                    role=role_entity,
                    status=status,
                    joined_at=now if status == MembershipStatus.ACTIVE.value else None,
                    created_at=now,
                    updated_at=now,
                )
            else:
                membership.role = role_entity
                membership.status = status
            if set_current and status == MembershipStatus.ACTIVE.value:
                user.current_business = business
            commit()

        _add()
