from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.enums import BillingUnit, BookingStatus, CancelledBy, DisputeStatus

ClientCancelReason = Literal[
    "cannot_use",
    "emergency",
    "equipment_broken",
    "equipment_damaged",
    "other",
]
OwnerCancelReason = Literal[
    "cannot_provide",
    "force_majeure",
    "returned_damaged",
    "client_no_show",
    "other",
]
CancelReason = ClientCancelReason | OwnerCancelReason


class EquipmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    brand: str
    image_url: str
    price_per_hour: Decimal | None
    price_per_day: Decimal | None
    timezone: str
    owner_id: int | None


class BookingCreate(BaseModel):
    equipment_id: int
    start_at: AwareDatetime
    end_at: AwareDatetime
    quantity: int = Field(default=1, ge=1)
    billing_unit: BillingUnit

    @model_validator(mode="after")
    def check_period(self) -> "BookingCreate":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be greater than start_at")
        return self


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    equipment_id: int
    start_at: datetime
    end_at: datetime
    picked_up_at: datetime | None
    returned_at: datetime | None
    quantity: int
    billing_unit: BillingUnit
    unit_price: Decimal
    total_price: Decimal
    status: BookingStatus
    cancelled_at: datetime | None
    cancelled_by: CancelledBy | None
    cancellation_reason: str | None
    penalty_amount: Decimal
    refund_amount: Decimal
    compensation_amount: Decimal
    damage_amount: Decimal
    dispute_status: DisputeStatus
    no_show_deadline: datetime | None
    no_show_at: datetime | None
    created_at: datetime
    equipment: EquipmentBrief


class BookingPage(BaseModel):
    items: list[BookingRead]
    total: int
    limit: int
    offset: int
    pages: int


class CancelRequest(BaseModel):
    reason: CancelReason
    description: str | None = Field(default=None, max_length=1000)


class ReturnRequest(BaseModel):
    damage_reported: bool = False
    description: str | None = Field(default=None, max_length=1000)


class PriceOption(BaseModel):
    billing_unit: BillingUnit
    unit_price: Decimal | None
    units: int | None
    total: Decimal | None
    available: bool
    problems: list[str] = Field(default_factory=list)


class BookingPreview(BaseModel):
    equipment_id: int
    quantity: int
    options: list[PriceOption]
    recommended: BillingUnit | None


class BusyInterval(BaseModel):
    start_at: datetime
    end_at: datetime
    quantity: int


class AvailabilityResponse(BaseModel):
    equipment_id: int
    quantity: int
    timezone: str
    buffer_minutes: int
    from_at: datetime
    to_at: datetime
    busy: list[BusyInterval]
