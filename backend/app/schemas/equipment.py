from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EquipmentBase(BaseModel):
    owner_id: int | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    category: str = Field(min_length=1, max_length=100)
    brand: str = Field(default="", max_length=100)

    price_per_hour: Decimal | None = Field(default=None, ge=0)
    price_per_day: Decimal | None = Field(default=None, ge=0)
    min_hours: int = Field(default=1, ge=1)
    min_days: int = Field(default=1, ge=1)
    max_hours: int = Field(default=24, ge=1)
    max_days: int = Field(default=30, ge=1)

    quantity: int = Field(default=1, ge=0)
    buffer_minutes: int = Field(default=30, ge=0, le=1440)
    lead_time_minutes: int = Field(default=30, ge=0, le=43200)
    working_hours: dict[str, Any] | None = None
    timezone: str = "Europe/Moscow"

    specs: dict[str, Any] = Field(default_factory=dict)
    image_url: str = ""

    @model_validator(mode="after")
    def check_prices_and_ranges(self) -> "EquipmentBase":
        if self.price_per_hour is None and self.price_per_day is None:
            raise ValueError("Нужна хотя бы одна цена: за час или за сутки")
        if self.max_hours < self.min_hours:
            raise ValueError("max_hours должен быть не меньше min_hours")
        if self.max_days < self.min_days:
            raise ValueError("max_days должен быть не меньше min_days")
        return self


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    owner_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, max_length=100)
    price_per_hour: Decimal | None = Field(default=None, ge=0)
    price_per_day: Decimal | None = Field(default=None, ge=0)
    min_hours: int | None = Field(default=None, ge=1)
    min_days: int | None = Field(default=None, ge=1)
    max_hours: int | None = Field(default=None, ge=1)
    max_days: int | None = Field(default=None, ge=1)
    quantity: int | None = Field(default=None, ge=0)
    buffer_minutes: int | None = Field(default=None, ge=0, le=1440)
    lead_time_minutes: int | None = Field(default=None, ge=0, le=43200)
    working_hours: dict[str, Any] | None = None
    timezone: str | None = None
    specs: dict[str, Any] | None = None
    image_url: str | None = None
    is_active: bool | None = None


class EquipmentRead(EquipmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EquipmentPage(BaseModel):
    items: list[EquipmentRead]
    total: int
    limit: int
    offset: int
    pages: int
