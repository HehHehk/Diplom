import enum


class UserRole(str, enum.Enum):
    user = "user"
    owner = "owner"
    admin = "admin"


class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    terminated = "terminated"
    no_show = "no_show"


class BillingUnit(str, enum.Enum):
    hour = "hour"
    day = "day"


class CancelledBy(str, enum.Enum):
    user = "user"
    owner = "owner"
    admin = "admin"
    system = "system"


class DisputeStatus(str, enum.Enum):
    none = "none"
    pending = "pending"
    resolved = "resolved"


class ResolutionOutcome(str, enum.Enum):
    client_fault = "client_fault"
    owner_fault = "owner_fault"
    equipment_fault = "equipment_fault"
    force_majeure = "force_majeure"
    no_fault = "no_fault"


class InteractionType(str, enum.Enum):
    view = "view"
    favorite = "favorite"
    booking = "booking"


class EventType(str, enum.Enum):
    created = "created"
    picked_up = "picked_up"
    returned = "returned"
    cancelled = "cancelled"
    no_show = "no_show"
    dispute_opened = "dispute_opened"
    dispute_resolved = "dispute_resolved"
    penalty_applied = "penalty_applied"
    compensated = "compensated"
