from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import UserRole
from app.services import booking_service
from tests.helpers import auth_headers, create_equipment, create_user, login


def now() -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0)


def iso(moment: datetime) -> str:
    return moment.isoformat()


async def owner_context(client: AsyncClient, db: AsyncSession, email: str = "owner@example.com"):
    owner = await create_user(db, email=email, role=UserRole.owner)
    token = await login(client, email, "secret123")
    return owner, {"Authorization": f"Bearer {token}"}


async def book(
    client: AsyncClient,
    headers: dict[str, str],
    equipment_id: int,
    start: datetime,
    end: datetime,
    billing_unit: str = "hour",
) -> dict:
    response = await client.post(
        "/bookings",
        json={
            "equipment_id": equipment_id,
            "start_at": iso(start),
            "end_at": iso(end),
            "quantity": 1,
            "billing_unit": billing_unit,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def patch_booking(db: AsyncSession, booking_id: int, **fields) -> Booking:
    entity = await db.get(Booking, booking_id)
    for name, value in fields.items():
        setattr(entity, name, value)
    await db.commit()
    return entity


@pytest.mark.asyncio
async def test_early_pickup_is_free(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(db_session, owner_id=owner.id, price_per_hour="100.00")
    start, end = now() + timedelta(hours=3), now() + timedelta(hours=10)
    booking = await book(client, client_headers, item.id, start, end)

    response = await client.post(f"/bookings/{booking['id']}/pickup", headers=owner_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["picked_up_at"] is not None
    assert data["status"] == "confirmed"
    assert data["total_price"] == booking["total_price"]


@pytest.mark.asyncio
async def test_client_cannot_pickup(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, _ = await owner_context(client, db_session)
    item = await create_equipment(db_session, owner_id=owner.id, price_per_hour="100.00")
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=2), now() + timedelta(hours=5)
    )

    response = await client.post(f"/bookings/{booking['id']}/pickup", headers=client_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_pickup_twice_conflict(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(db_session, owner_id=owner.id, price_per_hour="100.00")
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=2), now() + timedelta(hours=5)
    )

    assert (
        await client.post(f"/bookings/{booking['id']}/pickup", headers=owner_headers)
    ).status_code == 200
    again = await client.post(f"/bookings/{booking['id']}/pickup", headers=owner_headers)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_early_return_refunds_unused_units(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(
        db_session, owner_id=owner.id, price_per_hour="100.00", buffer_minutes=0
    )
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=11)
    )
    assert booking["total_price"] == "1000.00"

    await patch_booking(
        db_session,
        booking["id"],
        start_at=now() - timedelta(hours=2, minutes=50),
        end_at=now() + timedelta(hours=7),
        picked_up_at=now() - timedelta(hours=2, minutes=50),
    )

    response = await client.post(
        f"/bookings/{booking['id']}/return", json={}, headers=owner_headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "terminated"
    assert data["refund_amount"] == "700.00"


@pytest.mark.asyncio
async def test_return_without_pickup_conflict(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(db_session, owner_id=owner.id, price_per_hour="100.00")
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=2), now() + timedelta(hours=5)
    )

    response = await client.post(
        f"/bookings/{booking['id']}/return", json={}, headers=owner_headers
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_on_time_return_completes(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(
        db_session, owner_id=owner.id, price_per_hour="100.00", buffer_minutes=0
    )
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=2), now() + timedelta(hours=12)
    )

    await patch_booking(
        db_session,
        booking["id"],
        start_at=now() - timedelta(hours=4),
        end_at=now() - timedelta(hours=1),
        picked_up_at=now() - timedelta(hours=4),
    )

    response = await client.post(
        f"/bookings/{booking['id']}/return", json={}, headers=owner_headers
    )
    data = response.json()
    assert data["status"] == "completed"
    assert data["refund_amount"] == "0.00"


@pytest.mark.asyncio
async def test_damage_reported_goes_to_dispute(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(
        db_session, owner_id=owner.id, price_per_hour="100.00", buffer_minutes=0
    )
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=11)
    )
    await client.post(f"/bookings/{booking['id']}/pickup", headers=owner_headers)

    response = await client.post(
        f"/bookings/{booking['id']}/return",
        json={
            "damage_reported": True,
            "description": "При возврате обнаружена трещина на корпусе, требуется оценка ущерба",
        },
        headers=owner_headers,
    )
    data = response.json()
    assert data["dispute_status"] == "pending"
    assert data["refund_amount"] == "0.00"


@pytest.mark.asyncio
async def test_no_show_before_deadline_conflict(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(db_session, owner_id=owner.id, price_per_hour="100.00")
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=3), now() + timedelta(hours=6)
    )

    response = await client.post(f"/bookings/{booking['id']}/no-show", headers=owner_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_no_show_charges_five_percent(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(db_session, owner_id=owner.id, price_per_hour="100.00")
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=11)
    )
    await patch_booking(
        db_session,
        booking["id"],
        start_at=now() - timedelta(hours=2),
        end_at=now() + timedelta(hours=2),
        no_show_deadline=now() - timedelta(hours=1),
    )

    response = await client.post(f"/bookings/{booking['id']}/no-show", headers=owner_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "no_show"
    assert data["penalty_amount"] == "50.00"
    assert data["refund_amount"] == "950.00"


@pytest.mark.asyncio
async def test_no_show_revoke(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner, owner_headers = await owner_context(client, db_session)
    item = await create_equipment(db_session, owner_id=owner.id, price_per_hour="100.00")
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=11)
    )
    await patch_booking(
        db_session,
        booking["id"],
        start_at=now() - timedelta(hours=2),
        end_at=now() + timedelta(hours=2),
        no_show_deadline=now() - timedelta(hours=1),
    )
    await client.post(f"/bookings/{booking['id']}/no-show", headers=owner_headers)

    response = await client.post(f"/bookings/{booking['id']}/no-show/revoke", headers=owner_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "confirmed"
    assert data["penalty_amount"] == "0.00"
    assert data["no_show_at"] is None


@pytest.mark.asyncio
async def test_scheduler_marks_due_no_shows(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(
        client, client_headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=5)
    )
    await patch_booking(
        db_session,
        booking["id"],
        start_at=now() - timedelta(hours=2),
        end_at=now() + timedelta(hours=2),
        no_show_deadline=now() - timedelta(minutes=30),
    )

    processed = await booking_service.apply_due_no_shows(db_session)
    assert processed == 1

    refreshed = await db_session.get(Booking, booking["id"])
    assert refreshed.status.value == "no_show"
