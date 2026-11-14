"""Content-based рекомендации и блок «популярное».

Косинусное сходство по векторам признаков: категория, бренд, цена и числовые
характеристики из `equipment.specs`. Без внешних ML-библиотек — алгоритм
объясним и работает на холодных данных.
"""

from datetime import UTC, datetime, timedelta
from math import sqrt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import BookingStatus, InteractionType
from app.models.equipment import Equipment
from app.models.interaction import Interaction

POPULAR_DAYS = 30
VIEW_WEIGHT = 0.3
ACTIVE_BOOKING_STATUSES = (
    BookingStatus.confirmed,
    BookingStatus.completed,
    BookingStatus.terminated,
)


def _normalize(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    if high - low < 1e-9:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _daily_price(item: Equipment) -> float:
    if item.price_per_day is not None:
        return float(item.price_per_day)
    if item.price_per_hour is not None:
        return float(item.price_per_hour) * 24
    return 0.0


def build_vectors(items: list[Equipment]) -> dict[int, list[float]]:
    categories = sorted({item.category for item in items})
    brands = sorted({item.brand for item in items if item.brand})

    numeric_keys: set[str] = set()
    for item in items:
        for key, value in (item.specs or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_keys.add(key)

    prices = _normalize([_daily_price(item) for item in items])
    spec_values: dict[str, list[float]] = {}
    for key in numeric_keys:
        raw = [
            float(item.specs.get(key, 0))
            if isinstance(item.specs.get(key, 0), (int, float))
            else 0.0
            for item in items
        ]
        spec_values[key] = _normalize(raw)

    vectors: dict[int, list[float]] = {}
    for index, item in enumerate(items):
        vector: list[float] = []
        vector.extend(1.0 if item.category == category else 0.0 for category in categories)
        vector.extend(1.0 if item.brand == brand else 0.0 for brand in brands)
        vector.append(prices[index])
        for key in sorted(numeric_keys):
            vector.append(spec_values[key][index])
        vectors[item.id] = vector
    return vectors


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    if dot == 0:
        return 0.0
    norm_left = sqrt(sum(a * a for a in left))
    norm_right = sqrt(sum(b * b for b in right))
    if norm_left == 0 or norm_right == 0:
        return 0.0
    return dot / (norm_left * norm_right)


async def active_equipment(db: AsyncSession) -> list[Equipment]:
    stmt = select(Equipment).where(Equipment.is_active.is_(True)).order_by(Equipment.id)
    return list((await db.scalars(stmt)).all())


async def similar_equipment(
    db: AsyncSession, equipment: Equipment, limit: int = 6
) -> list[tuple[Equipment, float]]:
    items = await active_equipment(db)
    if not items or equipment.id not in {item.id for item in items}:
        items = [equipment, *items]

    vectors = build_vectors(items)
    target = vectors[equipment.id]

    scored: list[tuple[Equipment, float]] = []
    for item in items:
        if item.id == equipment.id:
            continue
        scored.append((item, round(cosine(target, vectors[item.id]), 4)))

    scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    return scored[:limit]


async def popular_equipment(db: AsyncSession, limit: int = 6) -> list[tuple[Equipment, float]]:
    since = datetime.now(UTC) - timedelta(days=POPULAR_DAYS)

    bookings = dict(
        (
            await db.execute(
                select(Booking.equipment_id, func.count())
                .where(
                    Booking.start_at >= since,
                    Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                )
                .group_by(Booking.equipment_id)
            )
        ).all()
    )
    views = dict(
        (
            await db.execute(
                select(Interaction.equipment_id, func.count())
                .where(
                    Interaction.created_at >= since,
                    Interaction.type == InteractionType.view,
                )
                .group_by(Interaction.equipment_id)
            )
        ).all()
    )

    items = await active_equipment(db)
    scored = [
        (
            item,
            round(float(bookings.get(item.id, 0)) + VIEW_WEIGHT * float(views.get(item.id, 0)), 2),
        )
        for item in items
    ]
    scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    return scored[:limit]


async def for_equipment(
    db: AsyncSession, equipment: Equipment, limit: int = 6
) -> tuple[str, list[tuple[Equipment, float]]]:
    """Возвращает стратегию и пары (позиция, score)."""
    similar = await similar_equipment(db, equipment, limit)
    if similar and any(score > 0 for _, score in similar):
        return "content", similar
    popular = await popular_equipment(db, limit + 1)
    return "popular", [(item, score) for item, score in popular if item.id != equipment.id][:limit]
