from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    BillingUnit,
    BookingStatus,
    CancelledBy,
    DisputeStatus,
    ResolutionOutcome,
)

if TYPE_CHECKING:
    from app.models.booking_event import BookingEvent
    from app.models.equipment import Equipment
    from app.models.user import User


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="period_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_bookings_equipment_time", "equipment_id", "start_at", "end_at"),
        Index("ix_bookings_user_start", "user_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True
    )

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    billing_unit: Mapped[BillingUnit] = mapped_column(
        Enum(BillingUnit, name="billing_unit", native_enum=False, length=10),
        default=BillingUnit.day,
        nullable=False,
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", native_enum=False, length=20),
        default=BookingStatus.confirmed,
        nullable=False,
        index=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[CancelledBy | None] = mapped_column(
        Enum(CancelledBy, name="cancelled_by", native_enum=False, length=10), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    penalty_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    compensation_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    damage_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    dispute_status: Mapped[DisputeStatus] = mapped_column(
        Enum(DisputeStatus, name="dispute_status", native_enum=False, length=20),
        default=DisputeStatus.none,
        nullable=False,
        index=True,
    )
    dispute_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dispute_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_outcome: Mapped[ResolutionOutcome | None] = mapped_column(
        Enum(ResolutionOutcome, name="resolution_outcome", native_enum=False, length=30),
        nullable=True,
    )
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    no_show_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    no_show_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    no_show_cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    appeal_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="bookings", foreign_keys=[user_id])
    equipment: Mapped["Equipment"] = relationship(back_populates="bookings")
    events: Mapped[list["BookingEvent"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status == BookingStatus.confirmed
