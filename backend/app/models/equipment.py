from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.equipment_image import EquipmentImage
    from app.models.interaction import Interaction
    from app.models.user import User


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint(
            "price_per_hour IS NOT NULL OR price_per_day IS NOT NULL",
            name="price_present",
        ),
        CheckConstraint("min_hours > 0", name="min_hours_positive"),
        CheckConstraint("min_days > 0", name="min_days_positive"),
        CheckConstraint("max_hours >= min_hours", name="hours_range"),
        CheckConstraint("max_days >= min_days", name="days_range"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint(
            "price_per_hour IS NULL OR price_per_hour >= 0",
            name="hour_price_non_negative",
        ),
        CheckConstraint(
            "price_per_day IS NULL OR price_per_day >= 0",
            name="day_price_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String(100), default="", nullable=False, index=True)

    price_per_hour: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_per_day: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_hours: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    max_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    lead_time_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    working_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)

    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    cover_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_id])
    bookings: Mapped[list["Booking"]] = relationship(back_populates="equipment")
    interactions: Mapped[list["Interaction"]] = relationship(back_populates="equipment")
    images: Mapped[list["EquipmentImage"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )
