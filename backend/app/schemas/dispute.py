from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import DisputeStatus, ResolutionOutcome

DisputeReason = Literal[
    "appeal",
    "emergency",
    "equipment_broken",
    "equipment_damaged",
    "returned_damaged",
    "force_majeure",
    "other",
]


class DisputeCreate(BaseModel):
    reason: DisputeReason
    description: str = Field(min_length=10, max_length=2000)


class DisputeResolve(BaseModel):
    outcome: ResolutionOutcome
    penalty_amount: Decimal | None = Field(default=None, ge=0)
    refund_amount: Decimal | None = Field(default=None, ge=0)
    compensation_amount: Decimal | None = Field(default=None, ge=0)
    damage_amount: Decimal | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=2000)


class DisputeRead(BaseModel):
    booking_id: int
    equipment_id: int
    equipment_title: str
    client_email: str
    owner_email: str | None
    status: DisputeStatus
    reason: str | None
    description: str | None
    premoderated: bool
    created_at: datetime | None
    resolved_at: datetime | None
    outcome: ResolutionOutcome | None
    total_price: Decimal
    penalty_amount: Decimal
    refund_amount: Decimal
    compensation_amount: Decimal
    damage_amount: Decimal


class DisputePage(BaseModel):
    items: list[DisputeRead]
    total: int
    limit: int
    offset: int
    pages: int
