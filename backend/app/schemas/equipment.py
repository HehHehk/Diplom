from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EquipmentBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    category: str = Field(min_length=1, max_length=100)
    brand: str = Field(default="", max_length=100)
    price_per_day: Decimal = Field(gt=0)
    quantity: int = Field(default=1, ge=0)
    specs: dict[str, Any] = Field(default_factory=dict)
    image_url: str = ""


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, max_length=100)
    price_per_day: Decimal | None = Field(default=None, gt=0)
    quantity: int | None = Field(default=None, ge=0)
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
