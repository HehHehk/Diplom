from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from math import ceil
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking
from app.models.booking_event import BookingEvent
from app.models.enums import (
    BillingUnit,
    BookingStatus,
    CancelledBy,
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


# --- Цена ---------------------------------------------------------------


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
    """Возвращает (единицы, цена за единицу, итог)."""
    unit_price = (
        equipment.price_per_hour if billing_unit == BillingUnit.hour else equipment.price_per_day
    )
    if unit_price is None:
        raise _bad_request("Для выбранного тарифа цена не задана")

    units = calculate_units(start_at, end_at, billing_unit)
    total = (unit_price * units * quantity).quantize(Decimal("0.01"))
    return units, unit_price, total


# --- Рабочие часы --------------------------------------------------------


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
        raise _bad_request("В этот день выдача не работает")
    if not _inside(start_intervals, local_start.timetz().replace(tzinfo=None)):
        raise _bad_request(f"Выдача возможна только в рабочие часы ({equipment.timezone})")

    end_intervals = schedule.get(local_end.weekday(), [])
    if not end_intervals or not _inside(end_intervals, local_end.timetz().replace(tzinfo=None)):
        raise _bad_request("Возврат должен попадать в рабочие часы")


# --- Валидация -----------------------------------------------------------


def validate_period(
    equipment: Equipment,
    start_at: datetime,
    end_at: datetime,
    billing_unit: BillingUnit,
    quantity: int,
) -> None:
    now = utcnow()

    if start_at >= end_at:
        raise _bad_request("Начало аренды должно быть раньше окончания")

    lead = timedelta(minutes=equipment.lead_time_minutes)
    if start_at < now + lead:
        raise _bad_request(
            f"Бронировать можно не позднее чем за {equipment.lead_time_minutes} мин до начала"
        )

    horizon = timedelta(days=settings.booking_horizon_days)
    if start_at > now + horizon:
        raise _bad_request(f"Бронирование доступно не дальше {settings.booking_horizon_days} дней")

    if quantity < 1 or quantity > equipment.quantity:
        raise _bad_request(f"Доступно экземпляров: {equipment.quantity}")

    minutes = (end_at - start_at).total_seconds() / 60
    max_days = min(equipment.max_days, settings.max_rental_days)

    if billing_unit == BillingUnit.hour:
        if equipment.price_per_hour is None:
            raise _bad_request("Часовой тариф недоступен")
        if minutes < equipment.min_hours * 60:
            raise _bad_request(f"Минимальная аренда — {equipment.min_hours} ч")
        if minutes > equipment.max_hours * 60:
            raise _bad_request(f"Максимальная аренда по часам — {equipment.max_hours} ч")
    else:
        if equipment.price_per_day is None:
            raise _bad_request("Суточный тариф недоступен")
        if minutes < equipment.min_days * 1440:
            raise _bad_request(f"Минимальная аренда — {equipment.min_days} сут")
        if minutes > max_days * 1440:
            raise _bad_request(f"Максимальная аренда — {max_days} сут")

    validate_working_hours(equipment, start_at, end_at)


# --- Конфликты -----------------------------------------------------------


def effective_start():
    """Фактическое начало: при ранней выдаче оборудование занято раньше."""
    return func.least(Booking.start_at, func.coalesce(Booking.picked_up_at, Booking.start_at))


async def booked_quantity(
    db: AsyncSession,
    equipment_id: int,
    start_at: datetime,
    end_at: datetime,
    buffer_minutes: int,
    *,
    exclude_booking_id: int | None = None,
) -> int:
    buffer = timedelta(minutes=buffer_minutes)
    stmt = select(func.coalesce(func.sum(Booking.quantity), 0)).where(
        Booking.equipment_id == equipment_id,
        Booking.status == BookingStatus.confirmed,
        effective_start() < end_at + buffer,
        Booking.end_at > start_at - buffer,
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(Booking.id != exclude_booking_id)
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
    """Сериализует проверку и вставку брони для одной единицы оборудования."""
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
            "Недостаточно свободных экземпляров на выбранный период",
            {"requested": quantity, "free": free, "quantity": equipment.quantity},
        )


async def check_user_limits(
    db: AsyncSession,
    user: User,
    equipment: Equipment,
    start_at: datetime,
    end_at: datetime,
) -> None:
    """Лимит активных броней и запрет собственных пересечений на одну позицию."""
    now = utcnow()
    active = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.user_id == user.id,
            Booking.status == BookingStatus.confirmed,
            Booking.end_at > now,
        )
    )
    if int(active or 0) >= settings.max_active_bookings_per_user:
        raise _conflict(
            "Достигнут лимит активных броней",
            {"limit": settings.max_active_bookings_per_user},
        )

    duplicate = await db.scalar(
        select(Booking.id)
        .where(
            Booking.user_id == user.id,
            Booking.equipment_id == equipment.id,
            Booking.status == BookingStatus.confirmed,
            effective_start() < end_at,
            Booking.end_at > start_at,
        )
        .limit(1)
    )
    if duplicate is not None:
        raise _conflict(
            "У вас уже есть активная бронь этой позиции на пересекающийся период",
            {"booking_id": duplicate},
        )


# --- Создание, выдача и возврат ------------------------------------------


def no_show_deadline(start_at: datetime, end_at: datetime) -> datetime:
    """Адаптивное окно неявки: 25% длительности, от 15 минут до 2 часов."""
    minutes = (end_at - start_at).total_seconds() / 60
    window = minutes * settings.no_show_percent_of_duration / 100
    window = min(max(window, settings.no_show_min_minutes), settings.no_show_max_minutes)
    deadline = start_at + timedelta(minutes=window)
    limit = end_at - timedelta(minutes=5)
    return min(deadline, limit) if limit > start_at else start_at


async def create_booking(
    db: AsyncSession,
    user: User,
    equipment: Equipment,
    start_at: datetime,
    end_at: datetime,
    quantity: int,
    billing_unit: BillingUnit,
) -> Booking:
    if equipment.owner_id == user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя бронировать собственное оборудование",
        )

    validate_period(equipment, start_at, end_at, billing_unit, quantity)
    _, unit_price, total = price_for(equipment, start_at, end_at, billing_unit, quantity)

    await lock_equipment(db, equipment.id)
    await check_capacity(db, equipment, start_at, end_at, quantity)
    await check_user_limits(db, user, equipment, start_at, end_at)

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
        no_show_deadline=no_show_deadline(start_at, end_at),
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
        raise _conflict("Эту бронь нельзя отменить: текущий статус — " + booking.status.value)
    if booking.picked_up_at is not None:
        raise _conflict("Аренда уже началась — используйте досрочный возврат")
    if now >= booking.start_at:
        raise _conflict("Аренда уже началась — используйте досрочный возврат")

    cancelled_by = (
        CancelledBy.admin
        if actor.is_admin
        else CancelledBy.user
        if actor.id == booking.user_id
        else CancelledBy.owner
        if booking.equipment.owner_id == actor.id
        else CancelledBy.user
    )

    technical = now <= booking.created_at + timedelta(
        minutes=settings.technical_cancel_minutes
    ) and booking.start_at - now > timedelta(hours=settings.owner_late_cancel_hours)

    total = booking.total_price
    penalty = Decimal("0.00")
    compensation = Decimal("0.00")

    if (
        cancelled_by == CancelledBy.user
        and not technical
        and booking.start_at - now <= timedelta(hours=settings.client_cancel_deadline_hours)
    ):
        penalty = _percent(total, settings.client_late_cancel_percent)
    elif (
        cancelled_by == CancelledBy.owner
        and not technical
        and booking.start_at - now <= timedelta(hours=settings.owner_late_cancel_hours)
    ):
        compensation = _percent(total, settings.owner_compensation_percent)

    charge = penalty + compensation
    refund = total - penalty
    needs_admin = reason in ADMIN_REVIEW_REASONS and not actor.is_admin and charge > 0

    booking.status = BookingStatus.cancelled
    booking.cancelled_at = now
    booking.cancelled_by = cancelled_by
    booking.cancellation_reason = reason
    booking.appeal_deadline = now + timedelta(hours=settings.appeal_window_hours)

    if needs_admin:
        booking.penalty_amount = Decimal("0.00")
        booking.compensation_amount = Decimal("0.00")
        booking.refund_amount = Decimal("0.00")
    else:
        booking.penalty_amount = penalty
        booking.compensation_amount = compensation
        booking.refund_amount = refund
        if penalty > 0:
            client = await db.get(User, booking.user_id)
            if client is not None:
                client.penalties_count += 1
        if cancelled_by == CancelledBy.owner and not technical and reason != "force_majeure":
            actor.cancellations_count += 1

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
                "penalty": str(booking.penalty_amount),
                "refund": str(booking.refund_amount),
                "compensation": str(booking.compensation_amount),
                "needs_admin": needs_admin,
            },
        )
    )

    if needs_admin:
        from app.services import dispute_service

        await db.flush()
        await dispute_service.open_dispute(db, booking, actor, reason, description, charge)

    await db.commit()
    return await get_booking(db, booking.id)  # type: ignore[return-value]


# --- Выдача, возврат, неявка --------------------------------------------


def _require_owner(booking: Booking, actor: User) -> None:
    if not actor.is_admin and booking.equipment.owner_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Действие доступно только арендодателю позиции",
        )


async def pickup_booking(
    db: AsyncSession, booking: Booking, actor: User, at: datetime | None = None
) -> Booking:
    """Выдача оборудования. Ранняя выдача бесплатна, конец аренды не меняется."""
    _require_owner(booking, actor)
    now = at or utcnow()

    if booking.status != BookingStatus.confirmed:
        raise _conflict("Выдать можно только подтверждённую бронь")
    if booking.picked_up_at is not None:
        raise _conflict("Оборудование уже выдано")
    if now > booking.end_at:
        raise _conflict("Срок брони истёк — выдавать нечего")

    if now < booking.start_at:
        equipment = booking.equipment
        validate_working_hours(equipment, now, min(now + timedelta(minutes=1), booking.end_at))
        booked = await booked_quantity(
            db,
            equipment.id,
            now,
            booking.end_at,
            equipment.buffer_minutes,
            exclude_booking_id=booking.id,
        )
        if booked + booking.quantity > equipment.quantity:
            raise _conflict("Нельзя выдать раньше: оборудование занято другой бронью")

    booking.picked_up_at = now
    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=actor.id,
            type=EventType.picked_up,
            payload={
                "early": now < booking.start_at,
                "planned_start": booking.start_at.isoformat(),
                "picked_up_at": now.isoformat(),
            },
        )
    )
    await db.commit()
    return await get_booking(db, booking.id)  # type: ignore[return-value]


async def return_booking(
    db: AsyncSession,
    booking: Booking,
    actor: User,
    *,
    damage_reported: bool = False,
    description: str | None = None,
) -> Booking:
    """Возврат оборудования. За неиспользованные единицы начисляется возврат."""
    _require_owner(booking, actor)
    now = utcnow()

    if booking.status != BookingStatus.confirmed:
        raise _conflict("Возврат возможен только для активной брони")
    if booking.picked_up_at is None:
        raise _conflict("Сначала отметьте выдачу оборудования")
    if now < booking.picked_up_at:
        raise _conflict("Дата возврата раньше даты выдачи")

    effective_end = min(now, booking.end_at)
    paid_units = calculate_units(booking.start_at, booking.end_at, booking.billing_unit)
    used_units = calculate_units(booking.picked_up_at, effective_end, booking.billing_unit)
    refund_units = max(0, paid_units - used_units)
    refund = (booking.unit_price * refund_units * booking.quantity).quantize(Decimal("0.01"))

    early = now < booking.end_at
    late = now > booking.end_at + timedelta(minutes=settings.late_return_grace_minutes)
    late_penalty = Decimal("0.00")
    if late:
        overdue_units = calculate_units(booking.end_at, now, booking.billing_unit)
        late_penalty = (booking.unit_price * overdue_units * booking.quantity).quantize(
            Decimal("0.01")
        )
        refund_units = 0
        refund = Decimal("0.00")

    booking.returned_at = now
    booking.status = BookingStatus.terminated if early else BookingStatus.completed
    booking.appeal_deadline = now + timedelta(hours=settings.appeal_window_hours)
    booking.penalty_amount = late_penalty

    if damage_reported:
        booking.refund_amount = Decimal("0.00")
        from app.services import dispute_service

        await db.flush()
        await dispute_service.open_dispute(
            db,
            booking,
            actor,
            "returned_damaged",
            description,
            refund,
            force=True,
        )
    else:
        booking.refund_amount = refund
    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=actor.id,
            type=EventType.returned,
            payload={
                "early": early,
                "paid_units": paid_units,
                "used_units": used_units,
                "refund": str(booking.refund_amount),
                "damage_reported": damage_reported,
                "description": description,
            },
        )
    )
    await db.commit()
    return await get_booking(db, booking.id)  # type: ignore[return-value]


async def mark_no_show(
    db: AsyncSession, booking: Booking, actor: User | None = None, at: datetime | None = None
) -> Booking:
    """Фиксация неявки: штраф 5%, остаток возвращается."""
    if actor is not None:
        _require_owner(booking, actor)
    now = at or utcnow()
    deadline = booking.no_show_deadline or no_show_deadline(booking.start_at, booking.end_at)

    if booking.status != BookingStatus.confirmed:
        raise _conflict("Неявку можно отметить только для активной брони")
    if booking.picked_up_at is not None:
        raise _conflict("Оборудование было выдано — неявки нет")
    if now < deadline:
        raise _conflict("Окно неявки ещё не истекло")

    penalty = _percent(booking.total_price, settings.client_late_cancel_percent)
    booking.status = BookingStatus.no_show
    booking.no_show_at = now
    booking.cancelled_at = now
    booking.cancelled_by = CancelledBy.system
    booking.cancellation_reason = "client_no_show"
    booking.penalty_amount = penalty
    booking.refund_amount = booking.total_price - penalty
    booking.appeal_deadline = now + timedelta(hours=settings.appeal_window_hours)

    client = await db.get(User, booking.user_id)
    if client is not None:
        client.penalties_count += 1

    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=actor.id if actor else None,
            type=EventType.no_show,
            payload={
                "penalty": str(penalty),
                "refund": str(booking.refund_amount),
                "deadline": deadline.isoformat(),
            },
        )
    )
    await db.commit()
    return await get_booking(db, booking.id)  # type: ignore[return-value]


async def revoke_no_show(db: AsyncSession, booking: Booking, actor: User) -> Booking:
    """Арендодатель может снять неявку в течение часа после фиксации."""
    _require_owner(booking, actor)
    now = utcnow()

    if booking.status != BookingStatus.no_show:
        raise _conflict("Бронь не в статусе неявки")
    if booking.no_show_at is None or now > booking.no_show_at + timedelta(hours=1):
        raise _conflict("Срок снятия неявки истёк")
    if now >= booking.end_at:
        raise _conflict("Срок аренды истёк — снимать неявку поздно")

    equipment = booking.equipment
    booked = await booked_quantity(
        db,
        equipment.id,
        max(now, booking.start_at),
        booking.end_at,
        equipment.buffer_minutes,
        exclude_booking_id=booking.id,
    )
    if booked + booking.quantity > equipment.quantity:
        raise _conflict(
            "Слот уже занят другой бронью — снять неявку нельзя",
            {"free": max(0, equipment.quantity - booked)},
        )

    booking.status = BookingStatus.confirmed
    booking.no_show_cancelled_at = now
    booking.no_show_at = None
    booking.no_show_deadline = None
    booking.cancelled_at = None
    booking.cancelled_by = None
    booking.cancellation_reason = None
    booking.penalty_amount = Decimal("0.00")
    booking.refund_amount = Decimal("0.00")
    booking.appeal_deadline = None

    client = await db.get(User, booking.user_id)
    if client is not None and client.penalties_count > 0:
        client.penalties_count -= 1

    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=actor.id,
            type=EventType.no_show_revoked,
            payload={"revoked_at": now.isoformat()},
        )
    )
    await db.commit()
    return await get_booking(db, booking.id)  # type: ignore[return-value]


async def apply_due_no_shows(db: AsyncSession) -> int:
    """Пакетная обработка просроченных неявок. Вызывается планировщиком."""
    now = utcnow()
    stmt = select(Booking).where(
        Booking.status == BookingStatus.confirmed,
        Booking.picked_up_at.is_(None),
        Booking.no_show_cancelled_at.is_(None),
        or_(
            and_(
                Booking.no_show_deadline.is_not(None),
                Booking.no_show_deadline <= now,
            ),
            and_(
                Booking.no_show_deadline.is_(None),
                Booking.start_at <= now - timedelta(minutes=settings.no_show_min_minutes),
            ),
        ),
    )
    bookings = list((await db.scalars(stmt)).all())
    processed = 0
    for booking in bookings:
        deadline = booking.no_show_deadline or no_show_deadline(booking.start_at, booking.end_at)
        if deadline > now:
            continue
        await mark_no_show(db, booking, None, now)
        processed += 1
    return processed


EARLY_RETURN_REASONS = {"equipment_broken", "equipment_damaged", "emergency", "other"}


async def request_early_return(
    db: AsyncSession,
    booking: Booking,
    actor: User,
    reason: str,
    description: str | None,
) -> Booking:
    """Клиент сообщает о поломке или ЧП во время аренды — решение за админом."""
    if booking.user_id != actor.id and not actor.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Досрочный возврат запрашивает арендатор",
        )
    if reason not in EARLY_RETURN_REASONS:
        raise _bad_request("Недопустимая причина досрочного возврата")
    if booking.status != BookingStatus.confirmed:
        raise _conflict("Бронь не активна")
    if booking.picked_up_at is None:
        raise _conflict("Сначала получите оборудование — до выдачи используйте отмену")

    now = utcnow()
    if now >= booking.end_at:
        raise _conflict("Аренда уже завершилась — оформите возврат через арендодателя")

    effective_end = min(now, booking.end_at)
    paid_units = calculate_units(booking.start_at, booking.end_at, booking.billing_unit)
    used_units = calculate_units(booking.picked_up_at, effective_end, booking.billing_unit)
    refund_units = max(0, paid_units - used_units)
    potential_refund = (booking.unit_price * refund_units * booking.quantity).quantize(
        Decimal("0.01")
    )

    booking.returned_at = now
    booking.status = BookingStatus.terminated
    booking.refund_amount = Decimal("0.00")
    booking.penalty_amount = Decimal("0.00")
    booking.appeal_deadline = None

    from app.services import dispute_service

    await db.flush()
    await dispute_service.open_dispute(
        db, booking, actor, reason, description, potential_refund, force=True
    )

    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=actor.id,
            type=EventType.returned,
            payload={
                "early": True,
                "initiated_by": "client",
                "reason": reason,
                "description": description,
                "potential_refund": str(potential_refund),
            },
        )
    )
    await db.commit()
    return await get_booking(db, booking.id)  # type: ignore[return-value]
