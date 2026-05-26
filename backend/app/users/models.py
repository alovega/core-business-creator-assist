from datetime import datetime

from pony.orm import Optional, Required, Set

from app.businesses.membership_status import MembershipStatus
from app.db import db

ACTIVE_STATUS = MembershipStatus.ACTIVE.value


class User(db.Entity):
    _table_ = "users"

    name = Required(str, max_len=255)
    email = Required(str, unique=True, max_len=255)
    password_hash = Required(str, max_len=255)
    is_active = Required(bool, default=True)
    current_business = Optional("Business")
    memberships = Set("BusinessMembership")
    memberships_invited = Set("BusinessMembership", reverse="invited_by")
    created_at = Required(datetime, default=datetime.now)
    updated_at = Required(datetime, default=datetime.now)

    @property
    def current_business_id(self) -> int | None:
        return self.current_business.id if self.current_business is not None else None

    @property
    def business_id(self) -> int | None:
        """Alias for current workspace (backward compatibility)."""
        return self.current_business_id

    def membership_for(self, business_id: int):
        from app.businesses.models import BusinessMembership

        return BusinessMembership.get(user=self, business=business_id)

    def active_membership_for(self, business_id: int):
        membership = self.membership_for(business_id)
        if membership is None:
            return None
        if membership.status != ACTIVE_STATUS:
            return None
        return membership

    def active_membership_for_current_business(self):
        if self.current_business_id is None:
            return None
        return self.active_membership_for(self.current_business_id)

    @property
    def role(self) -> str | None:
        membership = self.active_membership_for_current_business()
        return membership.role.key if membership is not None else None

    def has_permission(self, permission: str, business_id: int | None = None) -> bool:
        from app.common.rbac.permissions import membership_has_permission

        resolved_business_id = (
            business_id if business_id is not None else self.current_business_id
        )
        if resolved_business_id is None:
            return False
        membership = self.active_membership_for(resolved_business_id)
        return membership_has_permission(membership, permission)

    def to_dict(self) -> dict:
        membership = self.active_membership_for_current_business()
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": membership.role.key if membership is not None else None,
            "membership_status": membership.status if membership is not None else None,
            "current_business_id": self.current_business_id,
            "business_id": self.current_business_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }

    def __repr__(self) -> str:
        return f"<User {self.email}>"
