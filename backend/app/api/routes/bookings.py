import math
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import BillingUnit, InteractionType
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.booking import (
    BookingCreate,
    BookingPage,
    BookingPreview,
    BookingRead,
    CancelRequest,
    PriceOption,
    ReturnRequest,
)
from app.services import booking_service, equipment_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _ensure_aware(moment: datetime) -> None:
    if moment.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail="Время должно содержать часовой пояс (ISO 8601 со смещением)",
        )


@router.post("/preview", response_model=BookingPreview)
async def preview_booking(
    data: BookingCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BookingPreview:
    """Расчёт стоимости по обоим тарифам с проверкой доступности."""
    equipment = await equipment_service.get_equipment(db, data.equipment_id)
    if equipment is None:
        raise HTTPException(status_code=404, detail="Оборудование не найдено")

    options: list[PriceOption] = []
    for unit in (BillingUnit.hour, BillingUnit.day):
        unit_price = (
            equipment.price_per_hour if unit == BillingUnit.hour else equipment.price_per_day
        )
        if unit_price is None:
            continue

        problems: list[str] = []
        total: Decimal | None = None
        units: int | None = None
        try:
            booking_service.validate_period(
                equipment, data.start_at, data.end_at, unit, data.quantity
            )
        except HTTPException as exc:
            detail = exc.detail
            problems.append(detail if isinstance(detail, str) else str(detail))

        if not problems:
            units, _, total = booking_service.price_for(
                equipment, data.start_at, data.end_at, unit, data.quantity
            )
            booked = await booking_service.booked_quantity(
                db, equipment.id, data.start_at, data.end_at, equipment.buffer_minutes
            )
            if booked + data.quantity > equipment.quantity:
                problems.append("На выбранный период не хватает свободных экземпляров")

        options.append(
            PriceOption(
                billing_unit=unit,
                unit_price=unit_price,
                units=units,
                total=total,
                available=not problems,
                problems=problems,
            )
        )

    available = [option for option in options if option.available and option.total is not None]
    recommended = (
        min(available, key=lambda option: option.total or Decimal(0)).billing_unit
        if available
        else None
    )
    return BookingPreview(
        equipment_id=equipment.id,
        quantity=data.quantity,
        options=options,
        recommended=recommended,
    )


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    data: BookingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Booking:
    equipment = await equipment_service.get_equipment(db, data.equipment_id)
    if equipment is None:
        raise HTTPException(status_code=404, detail="Оборудование не найдено")

    booking = await booking_service.create_booking(
        db,
        user,
        equipment,
        data.start_at,
        data.end_at,
        data.quantity,
        data.billing_unit,
    )

    db.add(
        Interaction(
            user_id=user.id,
            equipment_id=equipment.id,
            type=InteractionType.booking,
        )
    )
    await db.commit()
    return booking


@router.get("/my", response_model=BookingPage)
async def my_bookings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BookingPage:
    filters = [Booking.user_id == user.id]
    total = await db.scalar(select(func.count()).select_from(Booking).where(*filters)) or 0
    stmt = (
        select(Booking)
        .where(*filters)
        .options(selectinload(Booking.equipment))
        .order_by(Booking.start_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.scalars(stmt)).all())
    return BookingPage(
        items=[BookingRead.model_validate(item) for item in items],
        total=int(total),
        limit=limit,
        offset=offset,
        pages=math.ceil(total / limit) if limit else 0,
    )


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Booking:
    booking = await booking_service.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена")

    is_owner = booking.equipment.owner_id == user.id
    if booking.user_id != user.id and not is_owner and not user.is_admin:
        raise HTTPException(status_code=403, detail="Нет доступа к этой брони")
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: int,
    data: CancelRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Booking:
    booking = await booking_service.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена")

    is_owner = booking.equipment.owner_id == user.id
    if booking.user_id != user.id and not is_owner and not user.is_admin:
        raise HTTPException(status_code=403, detail="Нет доступа к этой брони")

    return await booking_service.cancel_booking(db, booking, user, data.reason, data.description)


@router.post("/{booking_id}/pickup", response_model=BookingRead)
async def pickup_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Booking:
    """Выдача оборудования арендодателем. Ранняя выдача разрешена."""
    booking = await booking_service.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    return await booking_service.pickup_booking(db, booking, user)


@router.post("/{booking_id}/return", response_model=BookingRead)
async def return_booking(
    booking_id: int,
    data: ReturnRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Booking:
    """Возврат оборудования с пересчётом за неиспользованные единицы."""
    booking = await booking_service.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    return await booking_service.return_booking(
        db,
        booking,
        user,
        damage_reported=data.damage_reported,
        description=data.description,
    )


@router.post("/{booking_id}/no-show", response_model=BookingRead)
async def mark_no_show(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Booking:
    """Фиксация неявки клиента. Доступна после адаптивного окна ожидания."""
    booking = await booking_service.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    return await booking_service.mark_no_show(db, booking, user)


@router.post("/{booking_id}/no-show/revoke", response_model=BookingRead)
async def revoke_no_show(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Booking:
    """Снятие неявки арендодателем в течение часа."""
    booking = await booking_service.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    return await booking_service.revoke_no_show(db, booking, user)
