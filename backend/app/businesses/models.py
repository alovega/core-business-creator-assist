from datetime import datetime

from pony.orm import Json, Optional, PrimaryKey, Required, Set, composite_index

from app.businesses.membership_status import MembershipStatus
from app.db import db


class Business(db.Entity):
    _table_ = "businesses"

    name = Required(str, max_len=255)
    slug = Required(str, unique=True, max_len=255)
    phone_number = Optional(str, max_len=50)
    email = Optional(str, max_len=255)
    industry = Optional(str, max_len=100)
    plan = Required(str, default="free", max_len=50)
    status = Required(str, default="active", max_len=50)
    settings_json = Required(Json, default={})
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)
    memberships = Set("BusinessMembership")
    current_users = Set("User", reverse="current_business")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "phone_number": self.phone_number,
            "email": self.email,
            "industry": self.industry,
            "plan": self.plan,
            "status": self.status,
            "settings": self.settings_json or {},
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }

    def __repr__(self) -> str:
        return f"<Business {self.slug}>"


class BusinessMembership(db.Entity):
    _table_ = "business_memberships"

    user = Required("User")
    business = Required("Business")
    role = Required("Role")
    status = Required(str, default=MembershipStatus.ACTIVE.value, max_len=50)
    invited_by = Optional("User", reverse="memberships_invited")
    invited_at = Optional(datetime)
    joined_at = Optional(datetime)
    created_at = Required(datetime, default=datetime.utcnow)
    updated_at = Required(datetime, default=datetime.utcnow)

    composite_index(user, business)

    def to_dict(self, *, include_user: bool = True) -> dict:
        payload = {
            "id": self.id,
            "user_id": self.user.id,
            "business_id": self.business.id,
            "role": self.role.key,
            "status": self.status,
            "invited_by_id": self.invited_by.id if self.invited_by else None,
            "invited_at": self.invited_at.isoformat() + "Z" if self.invited_at else None,
            "joined_at": self.joined_at.isoformat() + "Z" if self.joined_at else None,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }
        if include_user:
            payload["user"] = {
                "id": self.user.id,
                "name": self.user.name,
                "email": self.user.email,
                "is_active": self.user.is_active,
            }
        return payload

    def __repr__(self) -> str:
        return (
            f"<BusinessMembership id={self.id} user={self.user.id} "
            f"business={self.business.id} role={self.role.key}>"
        )
