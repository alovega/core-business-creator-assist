"""Business membership lifecycle statuses."""

from enum import StrEnum


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"
    REMOVED = "removed"


ALL_MEMBERSHIP_STATUSES = frozenset(MembershipStatus)
ACTIVE_MEMBERSHIP_STATUSES = frozenset({MembershipStatus.ACTIVE})


def normalize_membership_status(status: str | None) -> MembershipStatus | None:
    if status is None:
        return None
    try:
        return MembershipStatus(status)
    except ValueError:
        return None
