from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import BillingUnit, BookingStatus
from app.models.user import User
from tests.helpers import auth_headers, create_equipment


async def add_booking(db: AsyncSession, user: User, equipment_id: int) -> None:
    start = datetime.now(UTC) - timedelta(days=2)
    db.add(
        Booking(
            user_id=user.id,
            equipment_id=equipment_id,
            start_at=start,
            end_at=start + timedelta(days=1),
            quantity=1,
            billing_unit=BillingUnit.day,
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            status=BookingStatus.completed,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_similar_items_rank_first(client: AsyncClient, db_session: AsyncSession):
    first = await create_equipment(
        db_session,
        title="Перфоратор Bosch",
        category="Инструмент",
        brand="Bosch",
        price_per_day="500.00",
        specs={"power_w": 800, "weight_kg": 2.7},
    )
    close = await create_equipment(
        db_session,
        title="Дрель Bosch",
        category="Инструмент",
        brand="Bosch",
        price_per_day="520.00",
        specs={"power_w": 750, "weight_kg": 2.5},
    )
    far = await create_equipment(
        db_session,
        title="Палатка",
        category="Туризм",
        brand="Naturehike",
        price_per_day="400.00",
        specs={"weight_kg": 4.2, "capacity_person": 4},
    )

    response = await client.get(f"/equipment/{first.id}/recommendations")
    assert response.status_code == 200
    data = response.json()
    assert data["strategy"] == "content"
    assert data["items"][0]["id"] == close.id
    assert far.id in [item["id"] for item in data["items"]]


@pytest.mark.asyncio
async def test_recommendations_exclude_self(client: AsyncClient, db_session: AsyncSession):
    item = await create_equipment(db_session)
    await create_equipment(db_session, title="Другая", category="Сад", price_per_day="300.00")

    response = await client.get(f"/equipment/{item.id}/recommendations")
    ids = [entry["id"] for entry in response.json()["items"]]
    assert item.id not in ids


@pytest.mark.asyncio
async def test_popular_orders_by_bookings(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    user = await db_session.scalar(select(User).where(User.email == "user@example.com"))
    first = await create_equipment(db_session, title="Хит", price_per_hour="100.00")
    second = await create_equipment(db_session, title="Средний", price_per_hour="100.00")
    await create_equipment(db_session, title="Новичок", price_per_hour="100.00")

    for _ in range(3):
        await add_booking(db_session, user, first.id)
    await add_booking(db_session, user, second.id)

    response = await client.get("/equipment/popular")
    assert response.status_code == 200
    data = response.json()
    assert data["strategy"] == "popular"
    ids = [item["id"] for item in data["items"]]
    assert ids.index(first.id) < ids.index(second.id)
    assert headers is not None


@pytest.mark.asyncio
async def test_cold_start_falls_back_to_popular(client: AsyncClient, db_session: AsyncSession):
    item = await create_equipment(db_session, title="Единственная")

    response = await client.get(f"/equipment/{item.id}/recommendations")
    data = response.json()
    assert data["strategy"] == "popular"
    assert data["items"] == []


@pytest.mark.asyncio
async def test_unknown_equipment_recommendations_404(client: AsyncClient):
    response = await client.get("/equipment/999999/recommendations")
    assert response.status_code == 404
