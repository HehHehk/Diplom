from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.booking import Booking
from app.models.booking_event import BookingEvent
from app.models.enums import (
    BookingStatus,
    DisputeStatus,
    EventType,
    ResolutionOutcome,
)
from app.models.equipment import Equipment
from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(UTC)


def _percent(amount: Decimal, percent: float) -> Decimal:
    return (amount * Decimal(str(percent)) / Decimal(100)).quantize(Decimal("0.01"))


def _bad(detail: str, code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _reset_window(user: User, now: datetime) -> None:
    window = timedelta(days=settings.dispute_premoderation_days)
    if user.disputes_window_start is None or now - user.disputes_window_start > window:
        user.disputes_window_start = now
        user.disputes_total_30d = 0
        user.disputes_rejected_30d = 0


def is_premoderated(user: User) -> bool:
    if user.disputes_total_30d < settings.dispute_premoderation_min_total:
        return False
    ratio = user.disputes_rejected_30d / user.disputes_total_30d
    return ratio > settings.dispute_premoderation_ratio


async def _recent_disputes(db: AsyncSession, actor_id: int, hours: int) -> int:
    since = utcnow() - timedelta(hours=hours)
    stmt = (
        select(func.count())
        .select_from(BookingEvent)
        .where(
            BookingEvent.actor_id == actor_id,
            BookingEvent.type == EventType.dispute_opened,
            BookingEvent.created_at >= since,
        )
    )
    return int(await db.scalar(stmt) or 0)


async def open_dispute(
    db: AsyncSession,
    booking: Booking,
    actor: User,
    reason: str,
    description: str | None,
    charge_amount: Decimal,
    *,
    force: bool = False,
) -> bool:
    """Открывает спор. Возвращает False, если спор не требуется (нечего оспаривать)."""
    if booking.dispute_status != DisputeStatus.none:
        raise _bad("По этой брони уже есть спор", status.HTTP_409_CONFLICT)

    text = (description or "").strip()
    if len(text) < settings.dispute_min_description:
        raise _bad(f"Описание должно содержать минимум {settings.dispute_min_description} символов")

    if charge_amount <= 0 and not force:
        return False

    now = utcnow()
    recent = await _recent_disputes(db, actor.id, hours=1)
    if recent >= settings.dispute_rate_per_hour:
        raise _bad("Слишком много обращений, попробуйте позже", status.HTTP_429_TOO_MANY_REQUESTS)

    _reset_window(actor, now)
    if actor.disputes_open >= settings.dispute_max_active:
        raise _bad(
            "Достигнут лимит активных споров — дождитесь решения по текущим",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if actor.disputes_total_30d >= settings.dispute_max_per_30d:
        raise _bad(
            "Достигнут месячный лимит обращений",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    premoderated = is_premoderated(actor)

    # Замораживаем суммы до решения: снимаем уже начисленный штраф из счётчика,
    # чтобы при отклонении спора не посчитать его дважды.
    if booking.penalty_amount > 0:
        client = await db.get(User, booking.user_id)
        if client is not None and client.penalties_count > 0:
            client.penalties_count -= 1

    booking.dispute_status = DisputeStatus.pending
    booking.dispute_reason = reason
    booking.dispute_description = text
    booking.dispute_created_at = now
    booking.dispute_premoderated = premoderated
    booking.penalty_amount = Decimal("0.00")
    booking.compensation_amount = Decimal("0.00")
    booking.refund_amount = Decimal("0.00")
    booking.appeal_deadline = None

    actor.disputes_open += 1
    actor.disputes_total_30d += 1

    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=actor.id,
            type=EventType.dispute_opened,
            payload={
                "reason": reason,
                "description": text,
                "charge": str(charge_amount),
                "premoderated": premoderated,
            },
        )
    )
    return True


async def _dispute_opener(db: AsyncSession, booking_id: int) -> int | None:
    stmt = (
        select(BookingEvent.actor_id)
        .where(
            BookingEvent.booking_id == booking_id,
            BookingEvent.type == EventType.dispute_opened,
        )
        .order_by(BookingEvent.created_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt)


async def resolve_dispute(
    db: AsyncSession,
    booking: Booking,
    admin: User | None,
    outcome: ResolutionOutcome,
    *,
    penalty: Decimal | None = None,
    refund: Decimal | None = None,
    compensation: Decimal | None = None,
    damage: Decimal | None = None,
    comment: str | None = None,
    automatic: bool = False,
) -> Booking:
    if booking.dispute_status != DisputeStatus.pending:
        raise _bad("Бронь не находится в споре", status.HTTP_409_CONFLICT)

    total = booking.total_price
    default_penalty = Decimal("0.00")
    default_refund = total
    default_compensation = Decimal("0.00")

    if outcome == ResolutionOutcome.client_fault:
        default_penalty = _percent(total, settings.client_late_cancel_percent)
        default_refund = total - default_penalty
    elif outcome in (ResolutionOutcome.owner_fault, ResolutionOutcome.equipment_fault):
        default_compensation = _percent(total, settings.owner_compensation_percent)
    elif outcome == ResolutionOutcome.force_majeure:
        default_refund = total

    booking.penalty_amount = penalty if penalty is not None else default_penalty
    booking.refund_amount = refund if refund is not None else default_refund
    booking.compensation_amount = compensation if compensation is not None else default_compensation
    booking.damage_amount = damage if damage is not None else booking.damage_amount

    total = booking.total_price
    if booking.penalty_amount + booking.refund_amount > total:
        raise _bad("Штраф и возврат в сумме не могут превышать стоимость брони")
    if booking.compensation_amount > total:
        raise _bad("Компенсация не может превышать стоимость брони")
    if booking.damage_amount < 0:
        raise _bad("Сумма ущерба не может быть отрицательной")

    booking.resolution_outcome = outcome
    booking.dispute_status = DisputeStatus.resolved
    booking.resolved_by = admin.id if admin else None
    booking.resolved_at = utcnow()
    booking.appeal_deadline = None

    opener_id = await _dispute_opener(db, booking.id)
    if opener_id is not None:
        opener = await db.get(User, opener_id)
        if opener is not None and opener.disputes_open > 0:
            opener.disputes_open -= 1
        if opener is not None and outcome == ResolutionOutcome.client_fault:
            opener.disputes_rejected_30d += 1

    client = await db.get(User, booking.user_id)
    owner = booking.equipment.owner

    if outcome == ResolutionOutcome.client_fault:
        if client is not None and booking.penalty_amount > 0:
            client.penalties_count += 1
    elif outcome == ResolutionOutcome.owner_fault and owner is not None:
        owner.cancellations_count += 1
        owner.incidents_count += 1
    elif outcome == ResolutionOutcome.equipment_fault and owner is not None:
        owner.incidents_count += 1

    if damage and damage > 0 and client is not None:
        client.damage_count += 1

    db.add(
        BookingEvent(
            booking_id=booking.id,
            actor_id=admin.id if admin else None,
            type=EventType.dispute_resolved,
            payload={
                "outcome": outcome.value,
                "penalty": str(booking.penalty_amount),
                "refund": str(booking.refund_amount),
                "compensation": str(booking.compensation_amount),
                "damage": str(booking.damage_amount),
                "comment": comment,
                "automatic": automatic,
            },
        )
    )
    await db.commit()
    return booking


async def apply_dispute_sla(db: AsyncSession) -> int:
    """48 часов без решения: штраф снимается, требования по ущербу остаются."""
    now = utcnow()
    deadline = now - timedelta(hours=settings.dispute_sla_hours)
    stmt = (
        select(Booking)
        .where(
            Booking.dispute_status == DisputeStatus.pending,
            Booking.dispute_created_at.is_not(None),
            Booking.dispute_created_at <= deadline,
            Booking.dispute_premoderated.is_(False),
            Booking.dispute_reason != "returned_damaged",
        )
        .options(
            selectinload(Booking.user),
            selectinload(Booking.equipment).selectinload(Equipment.owner),
        )
    )
    bookings = list((await db.scalars(stmt)).all())
    for booking in bookings:
        await resolve_dispute(
            db,
            booking,
            None,
            ResolutionOutcome.no_fault,
            penalty=Decimal("0.00"),
            refund=booking.total_price,
            compensation=Decimal("0.00"),
            damage=booking.damage_amount,
            comment="Автоматическое решение по истечении 48 часов",
            automatic=True,
        )
    return len(bookings)


def appeal_allowed(booking: Booking, now: datetime) -> bool:
    if booking.dispute_status != DisputeStatus.none:
        return False
    if booking.status == BookingStatus.confirmed:
        return False
    if booking.appeal_deadline is None or now > booking.appeal_deadline:
        return False
    return booking.penalty_amount + booking.compensation_amount + booking.damage_amount > 0


async def appeal_booking(
    db: AsyncSession, booking: Booking, actor: User, description: str | None
) -> Booking:
    now = utcnow()
    if not appeal_allowed(booking, now):
        raise _bad(
            "Оспорить можно только решение с суммами в течение 24 часов",
            status.HTTP_409_CONFLICT,
        )
    charge = booking.penalty_amount + booking.compensation_amount + booking.damage_amount
    await open_dispute(db, booking, actor, "appeal", description, charge)
    await db.commit()
    return booking
