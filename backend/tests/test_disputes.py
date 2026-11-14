from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.booking_event import BookingEvent
from app.models.enums import DisputeStatus, EventType
from app.models.user import User
from app.services import dispute_service
from tests.helpers import auth_headers, create_equipment


def now() -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0)


LONG_TEXT = (
    "Подробно описываю ситуацию: оборудование не подошло по условиям, прошу рассмотреть обращение"
)


async def book(
    client: AsyncClient, headers: dict[str, str], equipment_id: int, hours: int = 4
) -> dict:
    response = await client.post(
        "/bookings",
        json={
            "equipment_id": equipment_id,
            "start_at": (now() + timedelta(hours=1)).isoformat(),
            "end_at": (now() + timedelta(hours=1 + hours)).isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def cancel_as_emergency(
    client: AsyncClient, headers: dict[str, str], booking_id: int, text: str = LONG_TEXT
) -> dict:
    response = await client.post(
        f"/bookings/{booking_id}/cancel",
        json={"reason": "emergency", "description": text},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_emergency_cancel_opens_dispute(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)

    data = await cancel_as_emergency(client, headers, booking["id"])

    assert data["dispute_status"] == DisputeStatus.pending.value
    assert data["penalty_amount"] == "0.00"
    assert data["refund_amount"] == "0.00"


@pytest.mark.asyncio
async def test_short_description_rejected(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)

    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "emergency", "description": "коротко"},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_resolves_client_fault(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)
    await cancel_as_emergency(client, headers, booking["id"])

    queue = await client.get("/admin/disputes", headers=admin_headers)
    assert queue.status_code == 200
    assert queue.json()["total"] == 1

    response = await client.post(
        f"/admin/disputes/{booking['id']}/resolve",
        json={"outcome": "client_fault", "comment": "Уважительных причин нет"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "client_fault"
    assert data["penalty_amount"] == "20.00"
    assert data["refund_amount"] == "380.00"

    client_user = await db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert client_user.penalties_count == 1
    assert client_user.disputes_rejected_30d == 1


@pytest.mark.asyncio
async def test_admin_resolves_force_majeure(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)
    await cancel_as_emergency(client, headers, booking["id"])

    response = await client.post(
        f"/admin/disputes/{booking['id']}/resolve",
        json={"outcome": "force_majeure", "comment": "Справка предоставлена"},
        headers=admin_headers,
    )
    data = response.json()
    assert data["penalty_amount"] == "0.00"
    assert data["refund_amount"] == "400.00"


@pytest.mark.asyncio
async def test_non_admin_cannot_resolve(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)
    await cancel_as_emergency(client, headers, booking["id"])

    assert (await client.get("/admin/disputes", headers=headers)).status_code == 403
    response = await client.post(
        f"/admin/disputes/{booking['id']}/resolve",
        json={"outcome": "no_fault"},
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_resolve_twice_conflict(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)
    await cancel_as_emergency(client, headers, booking["id"])

    payload = {"outcome": "force_majeure"}
    first = await client.post(
        f"/admin/disputes/{booking['id']}/resolve", json=payload, headers=admin_headers
    )
    assert first.status_code == 200
    second = await client.post(
        f"/admin/disputes/{booking['id']}/resolve", json=payload, headers=admin_headers
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_active_dispute_limit(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    for index in range(4):
        item = await create_equipment(db_session, title=f"Позиция {index}", price_per_hour="100.00")
        booking = await book(client, headers, item.id)
        response = await client.post(
            f"/bookings/{booking['id']}/cancel",
            json={"reason": "emergency", "description": LONG_TEXT},
            headers=headers,
        )
        if index < 3:
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 429


@pytest.mark.asyncio
async def test_appeal_after_no_show(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)

    entity = await db_session.get(Booking, booking["id"])
    entity.start_at = now() - timedelta(hours=2)
    entity.end_at = now() + timedelta(hours=2)
    entity.no_show_deadline = now() - timedelta(hours=1)
    await db_session.commit()

    marked = await client.post(f"/bookings/{booking['id']}/no-show", headers=headers)
    assert marked.status_code == 403

    marked = await client.post(
        f"/bookings/{booking['id']}/no-show",
        headers=await auth_headers(client, db_session, admin=True),
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["penalty_amount"] == "20.00"

    response = await client.post(
        f"/bookings/{booking['id']}/appeal",
        json={"reason": "appeal", "description": LONG_TEXT},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["dispute_status"] == "pending"

    again = await client.post(
        f"/bookings/{booking['id']}/appeal",
        json={"reason": "appeal", "description": LONG_TEXT},
        headers=headers,
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_sla_resolves_after_48_hours(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)
    await cancel_as_emergency(client, headers, booking["id"])

    entity = await db_session.get(Booking, booking["id"])
    entity.dispute_created_at = now() - timedelta(hours=49)
    await db_session.commit()

    resolved = await dispute_service.apply_dispute_sla(db_session)
    assert resolved == 1

    await db_session.refresh(entity)
    assert entity.dispute_status.value == "resolved"
    assert entity.penalty_amount == 0
    assert entity.refund_amount == entity.total_price


@pytest.mark.asyncio
async def test_premoderation_blocks_sla(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)

    client_user = await db_session.scalar(select(User).where(User.email == "user@example.com"))
    client_user.disputes_total_30d = 6
    client_user.disputes_rejected_30d = 5
    client_user.disputes_window_start = now()
    await db_session.commit()

    await cancel_as_emergency(client, headers, booking["id"])

    entity = await db_session.get(Booking, booking["id"])
    assert entity.dispute_premoderated is True

    entity.dispute_created_at = now() - timedelta(hours=49)
    await db_session.commit()
    assert await dispute_service.apply_dispute_sla(db_session) == 0


@pytest.mark.asyncio
async def test_events_logged(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await book(client, headers, item.id)
    await cancel_as_emergency(client, headers, booking["id"])

    events = list(
        (
            await db_session.scalars(
                select(BookingEvent)
                .where(BookingEvent.booking_id == booking["id"])
                .order_by(BookingEvent.id)
            )
        ).all()
    )
    types = [event.type for event in events]
    assert EventType.created in types
    assert EventType.cancelled in types
    assert EventType.dispute_opened in types
