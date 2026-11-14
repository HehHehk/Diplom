from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import BillingUnit, BookingStatus
from app.models.user import User
from tests.helpers import create_equipment, create_user


async def add_usage(
    db: AsyncSession, user: User, equipment_id: int, start: datetime, status: BookingStatus
) -> None:
    db.add(
        Booking(
            user_id=user.id,
            equipment_id=equipment_id,
            start_at=start,
            end_at=start + timedelta(days=1),
            picked_up_at=start,
            returned_at=start + timedelta(days=1),
            quantity=1,
            billing_unit=BillingUnit.day,
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            status=status,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_forecast_counts_weekdays_and_hours(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, email="forecast@example.com")
    item = await create_equipment(db_session, price_per_day="100.00", timezone="UTC")

    monday = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
    await add_usage(db_session, user, item.id, monday, BookingStatus.completed)
    await add_usage(db_session, user, item.id, monday.replace(hour=12), BookingStatus.completed)
    await add_usage(
        db_session, user, item.id, monday + timedelta(days=1, hours=1), BookingStatus.terminated
    )

    response = await client.get(f"/equipment/{item.id}/load-forecast?days=365")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["total_bookings"] == 3
    monday_stat = next(stat for stat in data["by_weekday"] if stat["label"] == "Пн")
    assert monday_stat["count"] == 2
    assert data["best_weekday"] == "Пн"
    assert data["best_hours"] == [10, 11, 12]
    assert "понедельник" in data["recommendation"]


@pytest.mark.asyncio
async def test_forecast_empty(client: AsyncClient, db_session: AsyncSession):
    item = await create_equipment(db_session)
    response = await client.get(f"/equipment/{item.id}/load-forecast")
    data = response.json()
    assert data["total_bookings"] == 0
    assert data["best_weekday"] is None
    assert data["best_hours"] == []
    assert "Недостаточно данных" in data["recommendation"]


@pytest.mark.asyncio
async def test_forecast_period_filter(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, email="forecast2@example.com")
    item = await create_equipment(db_session, price_per_day="100.00", timezone="UTC")
    old = datetime.now(UTC) - timedelta(days=100)
    await add_usage(db_session, user, item.id, old, BookingStatus.completed)

    narrow = await client.get(f"/equipment/{item.id}/load-forecast?days=30")
    assert narrow.json()["total_bookings"] == 0

    wide = await client.get(f"/equipment/{item.id}/load-forecast?days=365")
    assert wide.json()["total_bookings"] == 1


@pytest.mark.asyncio
async def test_forecast_ignores_cancelled(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, email="forecast3@example.com")
    item = await create_equipment(db_session, price_per_day="100.00", timezone="UTC")
    await add_usage(
        db_session,
        user,
        item.id,
        datetime.now(UTC) - timedelta(days=3),
        BookingStatus.cancelled,
    )
    response = await client.get(f"/equipment/{item.id}/load-forecast")
    assert response.json()["total_bookings"] == 0


@pytest.mark.asyncio
async def test_forecast_unknown_equipment(client: AsyncClient):
    response = await client.get("/equipment/999999/load-forecast")
    assert response.status_code == 404
