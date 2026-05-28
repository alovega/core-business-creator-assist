"""Business membership helpers."""

from datetime import datetime

from pony.orm import commit

from app.businesses.membership_status import MembershipStatus

ACTIVE_STATUS = MembershipStatus.ACTIVE.value
from app.businesses.models import Business, BusinessMembership
from app.common.rbac.roles import ALL_ROLES, Role, get_system_role, normalize_role
from app.common.tenant import active_memberships, persist_current_business
from app.users.models import User


def get_membership(user: User, business_id: int) -> BusinessMembership | None:
    return BusinessMembership.get(user=user, business=business_id)


def get_active_membership(user: User, business_id: int) -> BusinessMembership | None:
    membership = get_membership(user, business_id)
    if membership is None:
        return None
    if membership.status != ACTIVE_STATUS:
        return None
    return membership


def list_accessible_businesses(user: User) -> list[dict]:
    memberships = active_memberships(user)
    memberships.sort(key=lambda m: m.business.name.lower())
    return [
        {
            **m.business.to_dict(),
            "role": m.role.key,
            "membership_status": m.status,
            "user_id": m.user.id,
            "business_id": m.business.id,
            "is_current": m.business.id == user.current_business_id,
        }
        for m in memberships
    ]


def get_membership_by_id(
    business: Business,
    membership_id: int,
) -> BusinessMembership | None:
    membership = BusinessMembership.get(id=membership_id)
    if membership is None or membership.business.id != business.id:
        return None
    return membership


def get_membership_for_business_user(
    business: Business,
    member_user_id: int,
) -> BusinessMembership | None:
    return BusinessMembership.get(user=member_user_id, business=business)


def create_owner_membership(
    user: User,
    business: Business,
    *,
    joined_at: datetime | None = None,
) -> BusinessMembership:
    owner_role = get_system_role(Role.OWNER.value)
    if owner_role is None:
        raise RuntimeError("System role 'owner' is not seeded")

    now = joined_at or datetime.utcnow()
    membership = BusinessMembership(
        user=user,
        business=business,
        role=owner_role,
        status=MembershipStatus.ACTIVE.value,
        joined_at=now,
        created_at=now,
        updated_at=now,
    )
    persist_current_business(user, business)
    return membership


def switch_workspace(user: User, business_id: int) -> Business:
    membership = get_active_membership(user, business_id)
    if membership is None:
        raise ValueError("No active membership for this business")
    persist_current_business(user, membership.business)
    return membership.business


def count_active_owners(business: Business) -> int:
    return sum(
        1
        for m in business.memberships
        if m.role.key == Role.OWNER.value and m.status == ACTIVE_STATUS
    )


def ensure_can_remove_or_demote_owner(business: Business, membership: BusinessMembership) -> str | None:
    if membership.role.key != Role.OWNER.value:
        return None
    if membership.status != ACTIVE_STATUS:
        return None
    if count_active_owners(business) <= 1:
        return "Every business must have at least one owner"
    return None


def invite_member(
    business: Business,
    *,
    email: str,
    role: str,
    invited_by: User,
) -> BusinessMembership:
    role_value = normalize_role(role)
    if role_value is None or role_value not in ALL_ROLES:
        raise ValueError(f"Invalid role: {role}")

    role_entity = get_system_role(role_value.value)
    if role_entity is None:
        raise RuntimeError(f"System role '{role_value.value}' is not seeded")

    invitee = User.get(email=email)
    if invitee is None:
        raise LookupError("User not found")

    existing = get_membership(invitee, business.id)
    if existing is not None:
        if existing.status == MembershipStatus.REMOVED.value:
            existing.role = role_entity
            existing.status = MembershipStatus.INVITED.value
            existing.invited_by = invited_by
            existing.invited_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            return existing
        raise ValueError("User is already a member of this business")

    now = datetime.utcnow()
    return BusinessMembership(
        user=invitee,
        business=business,
        role=role_entity,
        status=MembershipStatus.INVITED.value,
        invited_by=invited_by,
        invited_at=now,
        created_at=now,
        updated_at=now,
    )


def update_member_role(
    membership: BusinessMembership,
    *,
    role: str | None = None,
    status: str | None = None,
) -> None:
    business = membership.business

    if role is not None:
        role_value = normalize_role(role)
        if role_value is None or role_value not in ALL_ROLES:
            raise ValueError(f"Invalid role: {role}")
        role_entity = get_system_role(role_value.value)
        if role_entity is None:
            raise RuntimeError(f"System role '{role_value.value}' is not seeded")
        if membership.role.key == Role.OWNER.value and role_value != Role.OWNER:
            error = ensure_can_remove_or_demote_owner(business, membership)
            if error:
                raise ValueError(error)
        membership.role = role_entity

    if status is not None:
        status_value = MembershipStatus(status)
        if status_value == MembershipStatus.REMOVED and membership.role.key == Role.OWNER.value:
            error = ensure_can_remove_or_demote_owner(business, membership)
            if error:
                raise ValueError(error)
        membership.status = status_value.value
        if status_value == MembershipStatus.ACTIVE and membership.joined_at is None:
            membership.joined_at = datetime.utcnow()

    membership.updated_at = datetime.utcnow()


def remove_member(membership: BusinessMembership) -> None:
    update_member_role(membership, status=MembershipStatus.REMOVED.value)


def list_business_members(business: Business, *, include_removed: bool = False) -> list[BusinessMembership]:
    statuses = {s.value for s in MembershipStatus}
    if not include_removed:
        statuses -= {MembershipStatus.REMOVED.value}
    members = [
        m for m in business.memberships if m.status in statuses
    ]
    members.sort(key=lambda m: (m.user.name.lower(), m.user.email))
    return members


def accept_invitation(user: User, business_id: int) -> BusinessMembership:
    membership = get_membership(user, business_id)
    if membership is None or membership.status != MembershipStatus.INVITED.value:
        raise ValueError("No pending invitation for this business")
    membership.status = MembershipStatus.ACTIVE.value
    membership.joined_at = datetime.utcnow()
    membership.updated_at = datetime.utcnow()
    return membership
