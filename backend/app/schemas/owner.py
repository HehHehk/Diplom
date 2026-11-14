from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import UserRole


class OwnerStats(BaseModel):
    equipment_total: int
    equipment_active: int
    bookings_total: int
    bookings_active: int
    bookings_completed: int
    bookings_cancelled: int
    revenue: Decimal
    refunds: Decimal
    disputes_pending: int
    incidents: int


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    timezone: str
    timezone_source: str
    penalties_count: int
    cancellations_count: int
    incidents_count: int
    damage_count: int
    disputes_open: int
    disputes_total_30d: int
    disputes_rejected_30d: int
    moderation_mode: str
    is_abuser: bool
    created_at: datetime


class AdminUserUpdate(BaseModel):
    role: Literal["user", "owner", "admin"] | None = None
    is_active: bool | None = None
    is_abuser: bool | None = None
    moderation_mode: Literal["normal", "premoderation"] | None = None
    full_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "AdminUserUpdate":
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} не может быть null")
        return self


class AdminUserPage(BaseModel):
    items: list[AdminUserRead]
    total: int
    limit: int
    offset: int
    pages: int


class AdminStats(BaseModel):
    users: int
    owners: int
    equipment: int
    bookings: int
    bookings_active: int
    disputes_pending: int
    revenue: Decimal
