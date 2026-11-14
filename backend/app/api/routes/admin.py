import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import DisputeStatus
from app.models.equipment import Equipment
from app.models.user import User
from app.schemas.dispute import DisputePage, DisputeRead, DisputeResolve
from app.services import dispute_service

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_read(booking: Booking) -> DisputeRead:
    owner = booking.equipment.owner
    return DisputeRead(
        booking_id=booking.id,
        equipment_id=booking.equipment_id,
        equipment_title=booking.equipment.title,
        client_email=booking.user.email,
        owner_email=owner.email if owner else None,
        status=booking.dispute_status,
        reason=booking.dispute_reason,
        description=booking.dispute_description,
        premoderated=booking.dispute_premoderated,
        created_at=booking.dispute_created_at,
        resolved_at=booking.resolved_at,
        outcome=booking.resolution_outcome,
        total_price=booking.total_price,
        penalty_amount=booking.penalty_amount,
        refund_amount=booking.refund_amount,
        compensation_amount=booking.compensation_amount,
        damage_amount=booking.damage_amount,
    )


def _with_relations():
    return (
        selectinload(Booking.user),
        selectinload(Booking.equipment).selectinload(Equipment.owner),
    )


@router.get("/disputes", response_model=DisputePage)
async def list_disputes(
    status_filter: Literal["pending", "resolved", "all"] = Query(default="pending", alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> DisputePage:
    """Очередь споров для администратора."""
    filters = [Booking.dispute_status != DisputeStatus.none]
    if status_filter == "pending":
        filters.append(Booking.dispute_status == DisputeStatus.pending)
    elif status_filter == "resolved":
        filters.append(Booking.dispute_status == DisputeStatus.resolved)

    total = await db.scalar(select(func.count()).select_from(Booking).where(*filters)) or 0
    stmt = (
        select(Booking)
        .where(*filters)
        .options(*_with_relations())
        .order_by(Booking.dispute_created_at.asc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.scalars(stmt)).all())
    return DisputePage(
        items=[_to_read(booking) for booking in items],
        total=int(total),
        limit=limit,
        offset=offset,
        pages=math.ceil(total / limit) if limit else 0,
    )


@router.get("/disputes/{booking_id}", response_model=DisputeRead)
async def get_dispute(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> DisputeRead:
    booking = await _load(db, booking_id)
    return _to_read(booking)


@router.post("/disputes/{booking_id}/resolve", response_model=DisputeRead)
async def resolve_dispute(
    booking_id: int,
    data: DisputeResolve,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> DisputeRead:
    """Решение администратора по спору: суммы и виновная сторона."""
    booking = await _load(db, booking_id)
    await dispute_service.resolve_dispute(
        db,
        booking,
        admin,
        data.outcome,
        penalty=data.penalty_amount,
        refund=data.refund_amount,
        compensation=data.compensation_amount,
        damage=data.damage_amount,
        comment=data.comment,
    )
    booking = await _load(db, booking_id)
    return _to_read(booking)


async def _load(db: AsyncSession, booking_id: int) -> Booking:
    stmt = select(Booking).where(Booking.id == booking_id).options(*_with_relations())
    booking = await db.scalar(stmt)
    if booking is None or booking.dispute_status == DisputeStatus.none:
        raise HTTPException(status_code=404, detail="Спор не найден")
    return booking
