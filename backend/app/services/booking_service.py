from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from math import ceil
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking
from app.models.booking_event import BookingEvent
from app.models.enums import (
    BillingUnit,
    BookingStatus,
    CancelledBy,
    DisputeStatus,
    EventType,
)
from app.models.equipment import Equipment
from app.models.user import User

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

ADMIN_REVIEW_REASONS = {
    "emergency",
    "equipment_broken",
    "equipment_damaged",
    "force_majeure",
    "returned_damaged",
    "other",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _conflict(detail: str, extra: dict | None = None) -> HTTPException:
    payload: dict = {"message": detail}
    if extra:
        payload.update(extra)
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=payload)


# --- Р¦РµРЅР° ---------------------------------------------------------------


def calculate_units(start_at: datetime, end_at: datetime, billing_unit: BillingUnit) -> int:
    minutes = (end_at - start_at).total_seconds() / 60
    if billing_unit == BillingUnit.hour:
        return max(1, ceil(minutes / 60))
    return max(1, ceil(minutes / 1440))


def price_for(
    equipment: Equipment,
    start_at: datetime,
    end_at: datetime,
    billing_unit: BillingUnit,
    quantity: int,
) -> tuple[int, Decimal, Decimal]:
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ (РµРґРёРЅРёС†С‹, С†РµРЅР° Р·Р° РµРґРёРЅРёС†Сѓ, РёС‚РѕРі)."""
    unit_price = (
        equipment.price_per_hour if billing_unit == BillingUnit.hour else equipment.price_per_day
    )
    if unit_price is None:
        raise _bad_request("Р”Р»СЏ РІС‹Р±СЂР°РЅРЅРѕРіРѕ С‚Р°СЂРёС„Р° С†РµРЅР° РЅРµ Р·Р°РґР°РЅР°")

    units = calculate_units(start_at, end_at, billing_unit)
    total = (unit_price * units * quantity).quantize(Decimal("0.01"))
    return units, unit_price, total


# --- Р Р°Р±РѕС‡РёРµ С‡Р°СЃС‹ --------------------------------------------------------


def _parse_working_hours(raw: dict | None) -> dict[int, list[tuple[time, time]]]:
    if not raw:
        return {}
    parsed: dict[int, list[tuple[time, time]]] = {}
    for index, key in enumerate(WEEKDAYS):
        intervals = []
        for item in raw.get(key) or []:
            try:
                opens, closes = item
                intervals.append((time.fromisoformat(opens), time.fromisoformat(closes)))
            except (TypeError, ValueError):
                continue
        parsed[index] = intervals
    return parsed


def _inside(intervals: list[tuple[time, time]], moment: time) -> bool:
    return any(opens <= moment <= closes for opens, closes in intervals)


def validate_working_hours(equipment: Equipment, start_at: datetime, end_at: datetime) -> None:
    if not equipment.working_hours:
        return

    tz = ZoneInfo(equipment.timezone)
    local_start = start_at.astimezone(tz)
    local_end = end_at.astimezone(tz)
    schedule = _parse_working_hours(equipment.working_hours)

    start_intervals = schedule.get(local_start.weekday(), [])
    if not start_intervals:
        raise _bad_request("Р’ СЌС‚РѕС‚ РґРµРЅСЊ РІС‹РґР°С‡Р° РЅРµ СЂР°Р±РѕС‚Р°РµС‚")
    if not _inside(start_intervals, local_start.timetz().replace(tzinfo=None)):
        raise _bad_request(
            f"Р’С‹РґР°С‡Р° РІРѕР·РјРѕР¶РЅР° С‚РѕР»СЊРєРѕ РІ СЂР°Р±РѕС‡РёРµ С‡Р°СЃС‹ ({equipment.timezone})"
        )

    end_intervals = schedule.get(local_end.weekday(), [])
    if not end_intervals or not _inside(end_intervals, local_end.timetz().replace(tzinfo=None)):
        raise _bad_request(
            "Р’РѕР·РІСЂР°С‚ РґРѕР»Р¶РµРЅ РїРѕРїР°РґР°С‚СЊ РІ СЂР°Р±РѕС‡РёРµ С‡Р°СЃС‹"
        )


# --- Р’Р°Р»РёРґР°С†РёСЏ -----------------------------------------------------------


def validate_period(
    equipment: Equipment,
    start_at: datetime,
    end_at: datetime,
    billing_unit: BillingUnit,
    quantity: int,
) -> None:
    now = utcnow()

    if start_at >= end_at:
        raise _bad_request(
            "РќР°С‡Р°Р»Рѕ Р°СЂРµРЅРґС‹ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ СЂР°РЅСЊС€Рµ РѕРєРѕРЅС‡Р°РЅРёСЏ"
        )

    lead = timedelta(minutes=equipment.lead_time_minutes)
    if start_at < now + lead:
        raise _bad_request(
            f"Р‘СЂРѕРЅРёСЂРѕРІР°С‚СЊ РјРѕР¶РЅРѕ РЅРµ РїРѕР·РґРЅРµРµ С‡РµРј Р·Р° {equipment.lead_time_minutes} РјРёРЅ РґРѕ РЅР°С‡Р°Р»Р°"
        )

    horizon = timedelta(days=settings.booking_horizon_days)
    if start_at > now + horizon:
        raise _bad_request(
            f"Р‘СЂРѕРЅРёСЂРѕРІР°РЅРёРµ РґРѕСЃС‚СѓРїРЅРѕ РЅРµ РґР°Р»СЊС€Рµ {settings.booking_horizon_days} РґРЅРµР№"
        )

    if quantity < 1 or quantity > equipment.quantity:
        raise _bad_request(f"Р”РѕСЃС‚СѓРїРЅРѕ СЌРєР·РµРјРїР»СЏСЂРѕРІ: {equipment.quantity}")

    minutes = (end_at - start_at).total_seconds() / 60
    max_days = min(equipment.max_days, settings.max_rental_days)

    if billing_unit == BillingUnit.hour:
        if equipment.price_per_hour is None:
            raise _bad_request("Р§Р°СЃРѕРІРѕР№ С‚Р°СЂРёС„ РЅРµРґРѕСЃС‚СѓРїРµРЅ")
        if minutes < equipment.min_hours * 60:
            raise _bad_request(f"РњРёРЅРёРјР°Р»СЊРЅР°СЏ Р°СЂРµРЅРґР° вЂ” {equipment.min_hours} С‡")
        if minutes > equipment.max_hours * 60:
            raise _bad_request(
                f"РњР°РєСЃРёРјР°Р»СЊРЅР°СЏ Р°СЂРµРЅРґР° РїРѕ С‡Р°СЃР°Рј вЂ” {equipment.max_hours} С‡"
            )
    else:
        if equipment.price_per_day is None:
            raise _bad_request("РЎСѓС‚РѕС‡РЅС‹Р№ С‚Р°СЂРёС„ РЅРµРґРѕСЃС‚СѓРїРµРЅ")
        if minutes < equipment.min_days * 1440:
            raise _bad_request(
                f"РњРёРЅРёРјР°Р»СЊРЅР°СЏ Р°СЂРµРЅРґР° вЂ” {equipment.min_days} СЃСѓС‚"
            )
        if minutes > max_days * 1440:
            raise _bad_request(f"РњР°РєСЃРёРјР°Р»СЊРЅР°СЏ Р°СЂРµРЅРґР° вЂ” {max_days} СЃСѓС‚")

    validate_working_hours(equipment, start_at, end_at)


# --- РљРѕРЅС„Р»РёРєС‚С‹ -----------------------------------------------------------


def effective_start():
    """Р¤Р°РєС‚РёС‡РµСЃРєРѕРµ РЅР°С‡Р°Р»Рѕ: РїСЂРё СЂР°РЅРЅРµР№ РІС‹РґР°С‡Рµ РѕР±РѕСЂСѓРґРѕРІР°РЅРёРµ Р·Р°РЅСЏС‚Рѕ СЂР°РЅСЊС€Рµ."""
    return func.least(Booking.start_at, func.coalesce(Booking.picked_up_at, Booking.start_at))


async def booked_quantity(
    db: AsyncSession,
    equipment_id: int,
    start_at: datetime,
    end_at: datetime,
    buffer_minutes: int,
) -> int:
    buffer = timedelta(minutes=buffer_minutes)
    stmt = select(func.coalesce(func.sum(Booking.quantity), 0)).where(
        Booking.equipment_id == equipment_id,
        Booking.status == BookingStatus.confirmed,
        effective_start() < end_at + buffer,
        Booking.end_at > start_at - buffer,
    )
    return int(await db.scalar(stmt) or 0)


async def busy_intervals(
    db: AsyncSession,
    equipment_id: int,
    from_at: datetime,
    to_at: datetime,
) -> list[Booking]:
    stmt = (
        select(Booking)
        .where(
            Booking.equipment_id == equipment_id,
            Booking.status == BookingStatus.confirmed,
            Booking.start_at < to_at,
            Booking.end_at > from_at,
        )
        .order_by(Booking.start_at)
    )
    return list((await db.scalars(stmt)).all())


async def lock_equipment(db: AsyncSession, equipment_id: int) -> None:
    """РЎРµСЂРёР°Р»РёР·СѓРµС‚ РїСЂРѕРІРµСЂРєСѓ Рё РІСЃС‚Р°РІРєСѓ Р±СЂРѕРЅРё РґР»СЏ РѕРґРЅРѕР№ РµРґРёРЅРёС†С‹ РѕР±РѕСЂСѓРґРѕРІР°РЅРёСЏ."""
    await db.execute(select(Equipment.id).where(Equipment.id == equipment_id).with_for_update())


async def check_capacity(
    db: AsyncSession,
    equipment: Equipment,
    start_at: datetime,
    end_at: datetime,
    quantity: int,
) -> None:
    booked = await booked_quantity(db, equipment.id, start_at, end_at, equipment.buffer_minutes)
    if booked + quantity > equipment.quantity:
        free = max(0, equipment.quantity - booked)
        raise _conflict(
            "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ СЃРІРѕР±РѕРґРЅС‹С… СЌРєР·РµРјРїР»СЏСЂРѕРІ РЅР° РІС‹Р±СЂР°РЅРЅС‹Р№ РїРµСЂРёРѕРґ",
            {"requested": quantity, "free": free, "quantity": equipment.quantity},
        )


# --- РЎРѕР·РґР°РЅРёРµ Рё РѕС‚РјРµРЅР° ---------------------------------------------------


async def create_booking(
    db: AsyncSession,
    user: User,
    equipment: Equipment,
    start_at: datetime,
    end_at: datetime,
    quantity: int,
    billing_unit: BillingUnit,
) -> Booking:
    validate_period(equipment, start_at, end_at, billing_unit, quantity)
    _, unit_price, total = price_for(equipment, start_at, end_at, billing_unit, quantity)

    await lock_equipment(db, equipment.id)
    await check_capacity(db, equipment, start_at, end_at, quantity)

    booking = Booking(
        user_id=user.id,
        equipment_id=equipment.id,
        start_at=start_at,
        end_at=end_at,
        quantity=quantity,
        billing_unit=billing_unit,
        unit_price=unit_price,
        total_price=total,
        status=BookingStatus.confirmed,
    )
    db.add(booking)
    await db.flush()

    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=user.id,
            type=EventType.created,
            payload={
                "billing_unit": billing_unit.value,
                "units": calculate_units(start_at, end_at, billing_unit),
                "total_price": str(total),
            },
        )
    )
    await db.commit()
    return await get_booking(db, booking.id, with_relations=True)  # type: ignore[return-value]


async def get_booking(
    db: AsyncSession, booking_id: int, *, with_relations: bool = True
) -> Booking | None:
    from sqlalchemy.orm import selectinload

    stmt = select(Booking).where(Booking.id == booking_id)
    if with_relations:
        stmt = stmt.options(selectinload(Booking.equipment))
    return await db.scalar(stmt)


def _percent(amount: Decimal, percent: float) -> Decimal:
    return (amount * Decimal(str(percent)) / Decimal(100)).quantize(Decimal("0.01"))


async def cancel_booking(
    db: AsyncSession,
    booking: Booking,
    actor: User,
    reason: str,
    description: str | None,
) -> Booking:
    now = utcnow()

    if booking.status != BookingStatus.confirmed:
        raise _conflict(
            "Р­С‚Сѓ Р±СЂРѕРЅСЊ РЅРµР»СЊР·СЏ РѕС‚РјРµРЅРёС‚СЊ: С‚РµРєСѓС‰РёР№ СЃС‚Р°С‚СѓСЃ вЂ” "
            + booking.status.value
        )
    if booking.picked_up_at is not None:
        raise _conflict(
            "РђСЂРµРЅРґР° СѓР¶Рµ РЅР°С‡Р°Р»Р°СЃСЊ вЂ” РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РґРѕСЃСЂРѕС‡РЅС‹Р№ РІРѕР·РІСЂР°С‚"
        )
    if now >= booking.start_at:
        raise _conflict(
            "РђСЂРµРЅРґР° СѓР¶Рµ РЅР°С‡Р°Р»Р°СЃСЊ вЂ” РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РґРѕСЃСЂРѕС‡РЅС‹Р№ РІРѕР·РІСЂР°С‚"
        )

    cancelled_by = (
        CancelledBy.admin
        if actor.is_admin
        else CancelledBy.owner
        if actor.is_owner
        else CancelledBy.user
    )

    technical = now <= booking.created_at + timedelta(
        minutes=settings.technical_cancel_minutes
    ) and booking.start_at - now > timedelta(hours=settings.owner_late_cancel_hours)

    total = booking.total_price
    penalty = Decimal("0.00")
    compensation = Decimal("0.00")
    refund = total

    if reason in ADMIN_REVIEW_REASONS and not actor.is_admin:
        booking.dispute_status = DisputeStatus.pending
        booking.dispute_reason = reason
        booking.dispute_description = description
        refund = Decimal("0.00")
        penalty = Decimal("0.00")
        compensation = Decimal("0.00")
    elif cancelled_by == CancelledBy.user and not technical:
        if booking.start_at - now <= timedelta(hours=settings.client_cancel_deadline_hours):
            penalty = _percent(total, settings.client_late_cancel_percent)
            refund = total - penalty
    elif cancelled_by == CancelledBy.owner and not technical:
        if booking.start_at - now <= timedelta(hours=settings.owner_late_cancel_hours):
            compensation = _percent(total, settings.owner_compensation_percent)
        actor.cancellations_count += 1

    booking.status = BookingStatus.cancelled
    booking.cancelled_at = now
    booking.cancelled_by = cancelled_by
    booking.cancellation_reason = reason
    booking.penalty_amount = penalty
    booking.compensation_amount = compensation
    booking.refund_amount = refund

    if penalty > 0:
        client = await db.get(User, booking.user_id)
        if client is not None:
            client.penalties_count += 1

    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=actor.id,
            type=EventType.cancelled,
            payload={
                "reason": reason,
                "description": description,
                "cancelled_by": cancelled_by.value,
                "technical": technical,
                "penalty": str(penalty),
                "refund": str(refund),
                "compensation": str(compensation),
                "dispute": booking.dispute_status,
            },
        )
    )
    await db.commit()
    return await get_booking(db, booking.id)  # type: ignore[return-value]
