from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import BookingStatus
from app.models.equipment import Equipment

WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
WEEKDAY_FULL = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)
DEFAULT_PERIOD_DAYS = 90


def _weekday_index(pg_dow: int) -> int:
    """PostgreSQL: 0 — воскресенье, 6 — суббота. Приводим к Пн=0 … Вс=6."""
    return (int(pg_dow) + 6) % 7


async def load_forecast(
    db: AsyncSession, equipment: Equipment, days: int = DEFAULT_PERIOD_DAYS
) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    actual_start = func.coalesce(Booking.picked_up_at, Booking.start_at)
    local_start = func.timezone(equipment.timezone, actual_start)
    weekday = func.extract("dow", local_start)
    hour = func.extract("hour", local_start)

    stmt = (
        select(weekday.label("weekday"), hour.label("hour"), func.count().label("count"))
        .where(
            Booking.equipment_id == equipment.id,
            Booking.status.in_([BookingStatus.completed, BookingStatus.terminated]),
            actual_start >= since,
        )
        .group_by("weekday", "hour")
    )
    rows = (await db.execute(stmt)).all()

    weekday_counts = [0] * 7
    hour_counts = [0] * 24
    total = 0
    for row in rows:
        count = int(row.count)
        total += count
        weekday_counts[_weekday_index(row.weekday)] += count
        hour_counts[int(row.hour)] += count

    by_weekday = [
        {
            "weekday": index,
            "label": WEEKDAY_LABELS[index],
            "count": count,
            "share": round(count / total, 3) if total else 0.0,
        }
        for index, count in enumerate(weekday_counts)
    ]
    by_hour = [
        {
            "hour": hour_value,
            "count": count,
            "share": round(count / total, 3) if total else 0.0,
        }
        for hour_value, count in enumerate(hour_counts)
    ]

    best_weekday = None
    best_hours: list[int] = []
    recommendation = "Недостаточно данных: по этой позиции ещё не было завершённых аренд."

    if total:
        best_index = max(range(7), key=lambda index: weekday_counts[index])
        best_weekday = WEEKDAY_LABELS[best_index]
        ranked_hours = sorted(
            (hour_value for hour_value in range(24) if hour_counts[hour_value] > 0),
            key=lambda hour_value: (-hour_counts[hour_value], hour_value),
        )[:3]
        best_hours = sorted(ranked_hours)
        hours_text = ", ".join(f"{hour_value:02d}:00" for hour_value in best_hours)
        recommendation = (
            f"Чаще всего берут в {WEEKDAY_FULL[best_index]}. "
            f"Удобные часы выдачи: {hours_text} ({equipment.timezone})."
        )

    return {
        "equipment_id": equipment.id,
        "title": equipment.title,
        "period_days": days,
        "total_bookings": total,
        "by_weekday": by_weekday,
        "by_hour": by_hour,
        "best_weekday": best_weekday,
        "best_hours": best_hours,
        "recommendation": recommendation,
    }
