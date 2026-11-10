from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import InteractionType

if TYPE_CHECKING:
    from app.models.equipment import Equipment
    from app.models.user import User


class Interaction(Base):
    __tablename__ = "interactions"
    __table_args__ = (Index("ix_interactions_equipment_created", "equipment_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[InteractionType] = mapped_column(
        Enum(InteractionType, name="interaction_type", native_enum=False, length=20),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User | None"] = relationship(back_populates="interactions")
    equipment: Mapped["Equipment"] = relationship(back_populates="interactions")
