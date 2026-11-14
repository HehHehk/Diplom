from datetime import datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _validate_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Неизвестный часовой пояс") from exc
    return value


def _validate_working_hours(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("working_hours должен быть объектом по дням недели")
    for key, intervals in value.items():
        if key not in WEEKDAYS:
            raise ValueError(f"Неизвестный день недели: {key}")
        if not isinstance(intervals, list):
            raise TypeError(f"Интервалы дня {key} должны быть списком")
        for interval in intervals:
            if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                raise ValueError("Интервал должен быть парой [открытие, закрытие]")
            try:
                opens = time.fromisoformat(str(interval[0]))
                closes = time.fromisoformat(str(interval[1]))
            except ValueError as exc:
                raise ValueError("Время должно быть в формате HH:MM") from exc
            if opens >= closes:
                raise ValueError(f"В дне {key} открытие должно быть раньше закрытия")
    return value


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

    _tz = field_validator("timezone")(_validate_timezone)
    _hours = field_validator("working_hours")(_validate_working_hours)

    @model_validator(mode="after")
    def check_prices_and_ranges(self) -> "EquipmentBase":
        if self.price_per_hour is None and self.price_per_day is None:
            raise ValueError("Нужна хотя бы одна цена: за час или за сутки")
        if self.max_hours < self.min_hours:
            raise ValueError("max_hours должен быть не меньше min_hours")
        if self.max_days < self.min_days:
            raise ValueError("max_days должен быть не меньше min_days")
        if self.max_hours > settings.max_rental_days * 24:
            raise ValueError(f"max_hours не может превышать {settings.max_rental_days * 24} ч")
        if self.max_days > settings.max_rental_days:
            raise ValueError(f"max_days не может превышать {settings.max_rental_days} сут")
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

    _tz = field_validator("timezone")(_validate_timezone)
    _hours = field_validator("working_hours")(_validate_working_hours)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "EquipmentUpdate":
        nullable = {"price_per_hour", "price_per_day", "working_hours"}
        for name in self.model_fields_set:
            if name not in nullable and getattr(self, name) is None:
                raise ValueError(f"{name} не может быть null")
        for name in self.model_fields_set:
            if name == "owner_id" and getattr(self, name) is None:
                raise ValueError("owner_id не может быть null")
        return self

    @model_validator(mode="after")
    def check_caps(self) -> "EquipmentUpdate":
        if self.max_hours is not None and self.max_hours > settings.max_rental_days * 24:
            raise ValueError(f"max_hours не может превышать {settings.max_rental_days * 24} ч")
        if self.max_days is not None and self.max_days > settings.max_rental_days:
            raise ValueError(f"max_days не может превышать {settings.max_rental_days} сут")
        return self


class EquipmentRead(EquipmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EquipmentRecommendation(EquipmentRead):
    score: float = 0.0


class RecommendationList(BaseModel):
    strategy: str
    items: list[EquipmentRecommendation]


class EquipmentPage(BaseModel):
    items: list[EquipmentRead]
    total: int
    limit: int
    offset: int
    pages: int
