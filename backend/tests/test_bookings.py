from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DisputeStatus, UserRole
from tests.helpers import auth_headers, create_equipment, create_user


def moment(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    base = datetime.now(UTC) + timedelta(days=days, hours=hours, minutes=minutes)
    return base.replace(second=0, microsecond=0)


def payload(equipment_id: int, start: datetime, end: datetime, **extra) -> dict:
    body = {
        "equipment_id": equipment_id,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "quantity": extra.pop("quantity", 1),
        "billing_unit": extra.pop("billing_unit", "day"),
    }
    body.update(extra)
    return body


async def make_booking(
    client: AsyncClient,
    headers: dict[str, str],
    equipment_id: int,
    start: datetime,
    end: datetime,
    **extra,
) -> dict:
    response = await client.post(
        "/bookings", json=payload(equipment_id, start, end, **extra), headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_create_booking_daily_price(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_day="500.00")
    start, end = moment(days=2, hours=10), moment(days=3, hours=10)

    data = await make_booking(client, headers, item.id, start, end)

    assert data["total_price"] == "500.00"
    assert data["unit_price"] == "500.00"
    assert data["status"] == "confirmed"
    assert data["billing_unit"] == "day"


@pytest.mark.asyncio
async def test_create_booking_hourly_price(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_day=None, price_per_hour="100.00")
    start, end = moment(days=2, hours=10), moment(days=2, hours=13)

    data = await make_booking(client, headers, item.id, start, end, billing_unit="hour")

    assert data["total_price"] == "300.00"


@pytest.mark.asyncio
async def test_daily_price_rounds_up(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_day="500.00")
    start, end = moment(days=2, hours=10), moment(days=3, hours=12)

    data = await make_booking(client, headers, item.id, start, end)

    assert data["total_price"] == "1000.00"


@pytest.mark.asyncio
async def test_min_duration_enforced(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(
        db_session, price_per_day=None, price_per_hour="100.00", min_hours=2
    )
    start, end = moment(days=2, hours=10), moment(days=2, hours=11)

    response = await client.post(
        "/bookings", json=payload(item.id, start, end, billing_unit="hour"), headers=headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_max_duration_enforced(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(
        db_session, price_per_day=None, price_per_hour="100.00", max_hours=4
    )
    start, end = moment(days=2, hours=8), moment(days=2, hours=13)

    response = await client.post(
        "/bookings", json=payload(item.id, start, end, billing_unit="hour"), headers=headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_lead_time_enforced(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, lead_time_minutes=120)
    start, end = moment(hours=1), moment(hours=6)

    response = await client.post("/bookings", json=payload(item.id, start, end), headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_naive_datetime_rejected(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session)

    response = await client.post(
        "/bookings",
        json={
            "equipment_id": item.id,
            "start_at": "2030-01-01T10:00:00",
            "end_at": "2030-01-02T10:00:00",
            "billing_unit": "day",
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_capacity_conflict(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, quantity=1, buffer_minutes=0, price_per_hour="100.00")
    start, end = moment(days=2, hours=10), moment(days=2, hours=14)

    await make_booking(client, headers, item.id, start, end, billing_unit="hour")

    response = await client.post(
        "/bookings", json=payload(item.id, start, end, billing_unit="hour"), headers=headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["free"] == 0


@pytest.mark.asyncio
async def test_capacity_allows_second_unit(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, quantity=2, buffer_minutes=0, price_per_hour="100.00")
    start, end = moment(days=2, hours=10), moment(days=2, hours=14)

    await make_booking(client, headers, item.id, start, end, billing_unit="hour")
    await make_booking(client, headers, item.id, start, end, billing_unit="hour")

    response = await client.post(
        "/bookings", json=payload(item.id, start, end, billing_unit="hour"), headers=headers
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_buffer_blocks_adjacent_booking(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(
        db_session, quantity=1, buffer_minutes=30, price_per_hour="100.00"
    )
    first_start, first_end = moment(days=2, hours=10), moment(days=2, hours=12)

    await make_booking(client, headers, item.id, first_start, first_end, billing_unit="hour")

    too_close = await client.post(
        "/bookings",
        json=payload(item.id, first_end, moment(days=2, hours=14), billing_unit="hour"),
        headers=headers,
    )
    assert too_close.status_code == 409

    after_buffer = await client.post(
        "/bookings",
        json=payload(
            item.id,
            first_end + timedelta(minutes=30),
            moment(days=2, hours=15),
            billing_unit="hour",
        ),
        headers=headers,
    )
    assert after_buffer.status_code == 201


@pytest.mark.asyncio
async def test_working_hours_enforced(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    schedule = {
        day: [["09:00", "20:00"]] for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }
    item = await create_equipment(db_session, working_hours=schedule)
    day = datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(days=2)
    start = day.replace(hour=22, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    response = await client.post("/bookings", json=payload(item.id, start, end), headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_preview_recommends_cheaper_tariff(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(
        db_session, price_per_day="500.00", price_per_hour="100.00", min_hours=1
    )
    start, end = moment(days=2, hours=10), moment(days=2, hours=13)

    response = await client.post(
        "/bookings/preview", json=payload(item.id, start, end), headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["recommended"] == "hour"
    assert {option["billing_unit"] for option in data["options"]} == {"hour", "day"}


@pytest.mark.asyncio
async def test_availability_lists_busy_intervals(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, buffer_minutes=0, price_per_hour="100.00")
    start, end = moment(days=2, hours=10), moment(days=2, hours=14)
    await make_booking(client, headers, item.id, start, end, billing_unit="hour")

    response = await client.get(
        f"/equipment/{item.id}/availability",
        params={"from": moment(days=1).isoformat(), "to": moment(days=4).isoformat()},
    )
    assert response.status_code == 200
    assert len(response.json()["busy"]) == 1


@pytest.mark.asyncio
async def test_my_bookings(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session)
    await make_booking(client, headers, item.id, moment(days=2, hours=10), moment(days=3, hours=10))

    response = await client.get("/bookings/my", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["equipment"]["id"] == item.id


@pytest.mark.asyncio
async def test_cancel_early_no_penalty(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_day="1000.00")
    booking = await make_booking(
        client, headers, item.id, moment(days=3, hours=10), moment(days=4, hours=10)
    )

    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "cannot_use"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "cancelled"
    assert data["penalty_amount"] == "0.00"
    assert data["refund_amount"] == "1000.00"


@pytest.mark.asyncio
async def test_cancel_late_charges_five_percent(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_day="1000.00")
    booking = await make_booking(client, headers, item.id, moment(hours=1), moment(days=1, hours=1))

    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "cannot_use"},
        headers=headers,
    )
    data = response.json()
    assert data["penalty_amount"] == "50.00"
    assert data["refund_amount"] == "950.00"


@pytest.mark.asyncio
async def test_technical_cancel_window(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_day="1000.00")
    booking = await make_booking(
        client, headers, item.id, moment(days=5, hours=10), moment(days=6, hours=10)
    )

    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "cannot_use"},
        headers=headers,
    )
    data = response.json()
    assert data["penalty_amount"] == "0.00"
    assert data["refund_amount"] == "1000.00"


@pytest.mark.asyncio
async def test_cannot_cancel_after_start(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_day="1000.00")
    booking = await make_booking(
        client, headers, item.id, moment(days=2, hours=10), moment(days=3, hours=10)
    )

    from app.models.booking import Booking

    entity = await db_session.get(Booking, booking["id"])
    entity.start_at = datetime.now(UTC) - timedelta(minutes=5)
    entity.end_at = datetime.now(UTC) + timedelta(hours=2)
    await db_session.commit()

    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "cannot_use"},
        headers=headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_owner_cancellation_compensates(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner = await create_user(db_session, email="owner2@example.com", role=UserRole.owner)
    item = await create_equipment(db_session, price_per_day="1000.00", owner_id=owner.id)
    booking = await make_booking(
        client, client_headers, item.id, moment(hours=2), moment(days=1, hours=2)
    )

    owner_token = await client.post(
        "/auth/login", data={"username": "owner2@example.com", "password": "secret123"}
    )
    owner_headers = {"Authorization": f"Bearer {owner_token.json()['access_token']}"}

    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "cannot_provide"},
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["compensation_amount"] == "100.00"
    assert data["refund_amount"] == "1000.00"


@pytest.mark.asyncio
async def test_emergency_cancel_goes_to_dispute(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_day="1000.00")
    booking = await make_booking(client, headers, item.id, moment(hours=1), moment(days=1, hours=1))

    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "emergency", "description": "Попал в больницу, справка будет позже"},
        headers=headers,
    )
    data = response.json()
    assert data["dispute_status"] == DisputeStatus.pending.value
    assert data["penalty_amount"] == "0.00"
    assert data["refund_amount"] == "0.00"


@pytest.mark.asyncio
async def test_cannot_cancel_foreign_booking(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session)
    booking = await make_booking(
        client, headers, item.id, moment(days=2, hours=10), moment(days=3, hours=10)
    )

    stranger = await create_user(db_session, email="stranger@example.com")
    token = await client.post(
        "/auth/login", data={"username": "stranger@example.com", "password": "secret123"}
    )
    stranger_headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    assert stranger is not None

    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "cannot_use"},
        headers=stranger_headers,
    )
    assert response.status_code == 403
