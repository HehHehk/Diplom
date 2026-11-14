from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.interaction import Interaction


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=20),
        default=UserRole.user,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    timezone_source: Mapped[str] = mapped_column(String(20), default="fallback", nullable=False)

    # Репутация и ограничения
    penalties_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancellations_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incidents_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    damage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disputes_open: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disputes_total_30d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disputes_rejected_30d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disputes_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    moderation_mode: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    is_abuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="user", foreign_keys="Booking.user_id"
    )
    interactions: Mapped[list["Interaction"]] = relationship(back_populates="user")

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.admin

    @property
    def is_owner(self) -> bool:
        return self.role == UserRole.owner
