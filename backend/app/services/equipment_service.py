from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking
from app.models.enums import BookingStatus, InteractionType
from app.models.equipment import Equipment
from app.models.interaction import Interaction
from app.models.user import User

SORT_OPTIONS = {
    "newest": Equipment.created_at.desc(),
    "price_asc": func.coalesce(Equipment.price_per_day, Equipment.price_per_hour * 24).asc(),
    "price_desc": func.coalesce(Equipment.price_per_day, Equipment.price_per_hour * 24).desc(),
    "title": Equipment.title.asc(),
}


def effective_daily_price():
    """Для фильтров: суточная цена, для часовых позиций — 24 часовых."""
    return func.coalesce(Equipment.price_per_day, Equipment.price_per_hour * 24)


async def list_equipment(
    db: AsyncSession,
    *,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    owner_id: int | None = None,
    include_inactive: bool = False,
    sort: str = "newest",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Equipment], int]:
    filters = []
    if not include_inactive:
        filters.append(Equipment.is_active.is_(True))
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                Equipment.title.ilike(pattern),
                Equipment.description.ilike(pattern),
                Equipment.brand.ilike(pattern),
                Equipment.category.ilike(pattern),
            )
        )
    if category:
        filters.append(Equipment.category == category)
    if brand:
        filters.append(Equipment.brand == brand)
    if min_price is not None:
        filters.append(effective_daily_price() >= min_price)
    if max_price is not None:
        filters.append(effective_daily_price() <= max_price)
    if owner_id is not None:
        filters.append(Equipment.owner_id == owner_id)

    total = await db.scalar(select(func.count()).select_from(Equipment).where(*filters)) or 0

    order_by = SORT_OPTIONS.get(sort, SORT_OPTIONS["newest"])
    stmt = (
        select(Equipment)
        .where(*filters)
        .order_by(order_by, Equipment.id.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.scalars(stmt)).all())
    return items, int(total)


async def get_equipment(
    db: AsyncSession, equipment_id: int, *, include_inactive: bool = False
) -> Equipment | None:
    stmt = select(Equipment).where(Equipment.id == equipment_id)
    if not include_inactive:
        stmt = stmt.where(Equipment.is_active.is_(True))
    return await db.scalar(stmt)


async def list_categories(db: AsyncSession) -> list[str]:
    stmt = (
        select(Equipment.category)
        .where(Equipment.is_active.is_(True))
        .distinct()
        .order_by(Equipment.category)
    )
    return list((await db.scalars(stmt)).all())


async def log_view(db: AsyncSession, equipment_id: int, user_id: int | None) -> None:
    db.add(
        Interaction(
            equipment_id=equipment_id,
            user_id=user_id,
            type=InteractionType.view,
        )
    )
    await db.commit()


async def has_active_bookings(db: AsyncSession, equipment_id: int) -> bool:
    count = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.equipment_id == equipment_id,
            Booking.status == BookingStatus.confirmed,
        )
    )
    return bool(count)


async def resolve_owner(db: AsyncSession, owner_id: int) -> User:
    owner = await db.get(User, owner_id)
    if owner is None or not (owner.is_owner or owner.is_admin):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Владелец должен существовать и иметь роль арендодателя",
        )
    return owner


def validate_state(item: Equipment) -> None:
    """Проверяет итоговое состояние позиции после частичного редактирования."""

    def fail(detail: str) -> None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)

    if item.price_per_hour is None and item.price_per_day is None:
        fail("Нужна хотя бы одна цена: за час или за сутки")
    if item.min_hours > item.max_hours:
        fail("max_hours должен быть не меньше min_hours")
    if item.min_days > item.max_days:
        fail("max_days должен быть не меньше min_days")
    if item.max_hours > settings.max_rental_days * 24:
        fail(f"max_hours не может превышать {settings.max_rental_days * 24} ч")
    if item.max_days > settings.max_rental_days:
        fail(f"max_days не может превышать {settings.max_rental_days} сут")
    try:
        ZoneInfo(item.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Неизвестный часовой пояс",
        ) from exc
