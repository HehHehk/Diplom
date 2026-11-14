from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking
from app.models.enums import UserRole
from app.models.user import User
from app.services import booking_service, dispute_service
from tests.helpers import auth_headers, create_equipment, create_user, login

LONG_TEXT = (
    "Подробно описываю ситуацию и прошу рассмотреть обращение без штрафа по уважительной причине"
)


def now() -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0)


async def make_booking(
    client: AsyncClient,
    headers: dict[str, str],
    equipment_id: int,
    start: datetime,
    end: datetime,
) -> dict:
    response = await client.post(
        "/bookings",
        json={
            "equipment_id": equipment_id,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
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
async def test_duplicate_own_booking_blocked(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    item = await create_equipment(db_session, price_per_hour="100.00", buffer_minutes=0)
    start, end = now() + timedelta(hours=2), now() + timedelta(hours=5)

    await make_booking(client, headers, item.id, start, end)
    response = await client.post(
        "/bookings",
        json={
            "equipment_id": item.id,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
        headers=headers,
    )
    assert response.status_code == 409
    assert "message" in response.json()["detail"]


@pytest.mark.asyncio
async def test_active_bookings_limit(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "max_active_bookings_per_user", 2)
    headers = await auth_headers(client, db_session)
    start, end = now() + timedelta(hours=2), now() + timedelta(hours=4)

    first = await create_equipment(db_session, title="A", price_per_hour="100.00")
    second = await create_equipment(db_session, title="B", price_per_hour="100.00")
    third = await create_equipment(db_session, title="C", price_per_hour="100.00")

    await make_booking(client, headers, first.id, start, end)
    await make_booking(client, headers, second.id, start, end)

    response = await client.post(
        "/bookings",
        json={
            "equipment_id": third.id,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["limit"] == 2


@pytest.mark.asyncio
async def test_revoke_clears_deadline_and_scheduler(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await make_booking(
        client, headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=5)
    )
    await patch_booking(
        db_session,
        booking["id"],
        start_at=now() - timedelta(hours=2),
        end_at=now() + timedelta(hours=2),
        no_show_deadline=now() - timedelta(hours=1),
    )

    marked = await client.post(f"/bookings/{booking['id']}/no-show", headers=admin_headers)
    assert marked.status_code == 200

    revoked = await client.post(f"/bookings/{booking['id']}/no-show/revoke", headers=admin_headers)
    assert revoked.status_code == 200, revoked.text

    entity = await db_session.get(Booking, booking["id"])
    assert entity.no_show_deadline is None
    assert await booking_service.apply_due_no_shows(db_session) == 0


@pytest.mark.asyncio
async def test_revoke_blocked_when_slot_taken(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, price_per_hour="100.00", quantity=1)
    booking = await make_booking(
        client, headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=5)
    )
    await patch_booking(
        db_session,
        booking["id"],
        start_at=now() - timedelta(hours=2),
        end_at=now() + timedelta(hours=2),
        no_show_deadline=now() - timedelta(hours=1),
    )
    assert (
        await client.post(f"/bookings/{booking['id']}/no-show", headers=admin_headers)
    ).status_code == 200

    second = await create_user(db_session, email="second@example.com")
    token = await login(client, second.email, "secret123")
    second_headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        "/bookings",
        json={
            "equipment_id": item.id,
            "start_at": (now() + timedelta(hours=1)).isoformat(),
            "end_at": (now() + timedelta(hours=2)).isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
        headers=second_headers,
    )
    assert response.status_code == 201, response.text

    revoked = await client.post(f"/bookings/{booking['id']}/no-show/revoke", headers=admin_headers)
    assert revoked.status_code == 409


@pytest.mark.asyncio
async def test_force_majeure_does_not_increment_counter(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_user(db_session, email="owner@example.com", role=UserRole.owner)
    item = await create_equipment(db_session, owner_id=owner.id, price_per_hour="100.00")
    headers = await auth_headers(client, db_session)
    booking = await make_booking(
        client, headers, item.id, now() + timedelta(days=3), now() + timedelta(days=3, hours=4)
    )
    await patch_booking(db_session, booking["id"], created_at=now() - timedelta(hours=1))

    token = await login(client, owner.email, "secret123")
    owner_headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "force_majeure", "description": LONG_TEXT},
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text

    refreshed = await db_session.get(User, owner.id)
    assert refreshed.cancellations_count == 0


@pytest.mark.asyncio
async def test_appeal_freezes_and_no_double_penalty(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await make_booking(
        client, headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=5)
    )
    await patch_booking(
        db_session,
        booking["id"],
        start_at=now() - timedelta(hours=2),
        end_at=now() + timedelta(hours=2),
        no_show_deadline=now() - timedelta(hours=1),
    )
    assert (
        await client.post(f"/bookings/{booking['id']}/no-show", headers=admin_headers)
    ).status_code == 200

    user = await db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user.penalties_count == 1

    appeal = await client.post(
        f"/bookings/{booking['id']}/appeal",
        json={"reason": "appeal", "description": LONG_TEXT},
        headers=headers,
    )
    assert appeal.status_code == 200, appeal.text
    assert appeal.json()["penalty_amount"] == "0.00"
    assert appeal.json()["refund_amount"] == "0.00"

    await db_session.refresh(user)
    assert user.penalties_count == 0

    resolved = await client.post(
        f"/admin/disputes/{booking['id']}/resolve",
        json={"outcome": "client_fault"},
        headers=admin_headers,
    )
    assert resolved.status_code == 200, resolved.text
    await db_session.refresh(user)
    assert user.penalties_count == 1


@pytest.mark.asyncio
async def test_sla_skips_damage_dispute(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await make_booking(
        client, headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=5)
    )
    await client.post(f"/bookings/{booking['id']}/pickup", headers=admin_headers)
    returned = await client.post(
        f"/bookings/{booking['id']}/return",
        json={"damage_reported": True, "description": LONG_TEXT},
        headers=admin_headers,
    )
    assert returned.status_code == 200, returned.text

    await patch_booking(db_session, booking["id"], dispute_created_at=now() - timedelta(hours=49))
    assert await dispute_service.apply_dispute_sla(db_session) == 0


@pytest.mark.asyncio
async def test_resolve_rejects_amounts_above_total(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, price_per_hour="100.00")
    booking = await make_booking(
        client, headers, item.id, now() + timedelta(hours=1), now() + timedelta(hours=5)
    )
    await client.post(
        f"/bookings/{booking['id']}/cancel",
        json={"reason": "emergency", "description": LONG_TEXT},
        headers=headers,
    )
    response = await client.post(
        f"/admin/disputes/{booking['id']}/resolve",
        json={"outcome": "force_majeure", "refund_amount": "99999.00"},
        headers=admin_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_price_filter_includes_hourly_only(client: AsyncClient, db_session: AsyncSession):
    await create_equipment(
        db_session, title="Почасовой", price_per_day=None, price_per_hour="100.00"
    )
    wide = await client.get("/equipment", params={"max_price": 3000})
    assert wide.json()["total"] == 1
    narrow = await client.get("/equipment", params={"max_price": 2000})
    assert narrow.json()["total"] == 0


@pytest.mark.asyncio
async def test_availability_rejects_naive_datetime(client: AsyncClient, db_session: AsyncSession):
    item = await create_equipment(db_session)
    response = await client.get(
        f"/equipment/{item.id}/availability",
        params={"from": "2030-01-01T00:00:00", "to": "2030-01-02T00:00:00"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_rejects_explicit_nulls(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    response = await client.patch("/auth/me", json={"full_name": None}, headers=headers)
    assert response.status_code == 422

    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session)
    patch = await client.patch(f"/equipment/{item.id}", json={"title": None}, headers=admin_headers)
    assert patch.status_code == 422


@pytest.mark.asyncio
async def test_equipment_caps_and_timezone_validated(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    base = {
        "title": "Позиция",
        "category": "Инструмент",
        "price_per_hour": "100.00",
        "price_per_day": "500.00",
    }

    too_long = await client.post(
        "/owner/equipment",
        json={**base, "max_hours": settings.max_rental_days * 24 + 1},
        headers=headers,
    )
    assert too_long.status_code == 422

    bad_zone = await client.post(
        "/owner/equipment", json={**base, "timezone": "Mars/Base"}, headers=headers
    )
    assert bad_zone.status_code == 422

    bad_hours = await client.post(
        "/owner/equipment",
        json={**base, "working_hours": {"mon": [["20:00", "09:00"]]}},
        headers=headers,
    )
    assert bad_hours.status_code == 422


@pytest.mark.asyncio
async def test_patch_min_greater_than_max(client: AsyncClient, db_session: AsyncSession):
    admin_headers = await auth_headers(client, db_session, admin=True)
    item = await create_equipment(db_session, min_hours=1, max_hours=24)

    response = await client.patch(
        f"/equipment/{item.id}", json={"min_hours": 30}, headers=admin_headers
    )
    assert response.status_code == 422
