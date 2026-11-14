import math
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_owner
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import BookingStatus, DisputeStatus
from app.models.equipment import Equipment
from app.models.user import User
from app.schemas.booking import BookingPage, BookingRead
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentPage,
    EquipmentRead,
    EquipmentUpdate,
)
from app.schemas.owner import OwnerStats
from app.services import equipment_service

router = APIRouter(prefix="/owner", tags=["owner"])


@router.get("/equipment", response_model=EquipmentPage)
async def my_equipment(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    include_inactive: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> EquipmentPage:
    """Позиции арендодателя. Админ видит все."""
    owner_filter = None if user.is_admin else user.id
    items, total = await equipment_service.list_equipment(
        db,
        q=q,
        category=category,
        owner_id=owner_filter,
        include_inactive=include_inactive,
        sort="newest",
        limit=limit,
        offset=offset,
    )
    return EquipmentPage(
        items=[EquipmentRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        pages=math.ceil(total / limit) if limit else 0,
    )


@router.post("/equipment", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
async def create_my_equipment(
    data: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> Equipment:
    payload = data.model_dump()
    owner_id = payload.pop("owner_id")
    item = Equipment(**payload, owner_id=owner_id if user.is_admin and owner_id else user.id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/equipment/{equipment_id}", response_model=EquipmentRead)
async def update_my_equipment(
    equipment_id: int,
    data: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> Equipment:
    item = await equipment_service.get_equipment(db, equipment_id, include_inactive=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Оборудование не найдено")
    if not user.is_admin and item.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Можно редактировать только свои позиции")

    changes = data.model_dump(exclude_unset=True)
    if not user.is_admin:
        changes.pop("owner_id", None)
    for field, value in changes.items():
        setattr(item, field, value)

    if item.price_per_hour is None and item.price_per_day is None:
        raise HTTPException(status_code=422, detail="Нужна хотя бы одна цена")
    if item.min_hours > item.max_hours or item.min_days > item.max_days:
        raise HTTPException(status_code=422, detail="Минимальная длительность больше максимальной")

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/equipment/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_equipment(
    equipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> None:
    item = await equipment_service.get_equipment(db, equipment_id, include_inactive=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Оборудование не найдено")
    if not user.is_admin and item.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Можно удалять только свои позиции")

    active = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.equipment_id == item.id,
            Booking.status == BookingStatus.confirmed,
        )
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail="По позиции есть активные брони — сначала завершите их",
        )

    item.is_active = False
    await db.commit()


@router.get("/bookings", response_model=BookingPage)
async def my_bookings(
    status_filter: Literal[
        "confirmed", "completed", "cancelled", "terminated", "no_show", "all"
    ] = Query(default="all", alias="status"),
    from_at: datetime | None = Query(default=None),
    to_at: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> BookingPage:
    filters = []
    if not user.is_admin:
        filters.append(Equipment.owner_id == user.id)
    if status_filter != "all":
        filters.append(Booking.status == BookingStatus(status_filter))
    if from_at is not None:
        filters.append(Booking.start_at >= from_at)
    if to_at is not None:
        filters.append(Booking.end_at <= to_at)

    base = select(Booking).join(Equipment, Booking.equipment_id == Equipment.id).where(*filters)
    total = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .join(Equipment, Booking.equipment_id == Equipment.id)
        .where(*filters)
    )
    stmt = (
        base.options(selectinload(Booking.equipment))
        .order_by(Booking.start_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.scalars(stmt)).all())
    return BookingPage(
        items=[BookingRead.model_validate(item) for item in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
        pages=math.ceil((total or 0) / limit) if limit else 0,
    )


@router.get("/stats", response_model=OwnerStats)
async def stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> OwnerStats:
    owner_filter = [] if user.is_admin else [Equipment.owner_id == user.id]

    equipment_total = await db.scalar(
        select(func.count()).select_from(Equipment).where(*owner_filter)
    )
    equipment_active = await db.scalar(
        select(func.count())
        .select_from(Equipment)
        .where(*owner_filter, Equipment.is_active.is_(True))
    )

    def booking_count(*extra):
        return (
            select(func.count())
            .select_from(Booking)
            .join(Equipment, Booking.equipment_id == Equipment.id)
            .where(*owner_filter, *extra)
        )

    bookings_total = await db.scalar(booking_count())
    bookings_active = await db.scalar(booking_count(Booking.status == BookingStatus.confirmed))
    bookings_completed = await db.scalar(
        booking_count(Booking.status.in_([BookingStatus.completed, BookingStatus.terminated]))
    )
    bookings_cancelled = await db.scalar(
        booking_count(Booking.status.in_([BookingStatus.cancelled, BookingStatus.no_show]))
    )
    disputes_pending = await db.scalar(
        booking_count(Booking.dispute_status == DisputeStatus.pending)
    )
    revenue = await db.scalar(
        select(func.coalesce(func.sum(Booking.total_price), 0))
        .select_from(Booking)
        .join(Equipment, Booking.equipment_id == Equipment.id)
        .where(*owner_filter, Booking.status == BookingStatus.completed)
    )
    refunds = await db.scalar(
        select(func.coalesce(func.sum(Booking.refund_amount), 0))
        .select_from(Booking)
        .join(Equipment, Booking.equipment_id == Equipment.id)
        .where(*owner_filter)
    )

    return OwnerStats(
        equipment_total=int(equipment_total or 0),
        equipment_active=int(equipment_active or 0),
        bookings_total=int(bookings_total or 0),
        bookings_active=int(bookings_active or 0),
        bookings_completed=int(bookings_completed or 0),
        bookings_cancelled=int(bookings_cancelled or 0),
        revenue=Decimal(revenue or 0),
        refunds=Decimal(refunds or 0),
        disputes_pending=int(disputes_pending or 0),
        incidents=user.incidents_count,
    )
