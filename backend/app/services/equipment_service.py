from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InteractionType
from app.models.equipment import Equipment
from app.models.interaction import Interaction

SORT_OPTIONS = {
    "newest": Equipment.created_at.desc(),
    "price_asc": Equipment.price_per_day.asc(),
    "price_desc": Equipment.price_per_day.desc(),
    "title": Equipment.title.asc(),
}


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
        filters.append(Equipment.price_per_day >= min_price)
    if max_price is not None:
        filters.append(Equipment.price_per_day <= max_price)
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
