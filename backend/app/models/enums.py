import enum


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class BookingStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"


class InteractionType(str, enum.Enum):
    view = "view"
    favorite = "favorite"
    booking = "booking"
