from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from tests.helpers import auth_headers, create_equipment, create_user, login


def payload(title: str = "Мой перфоратор") -> dict:
    return {
        "title": title,
        "category": "Инструмент",
        "brand": "Bosch",
        "price_per_hour": "100.00",
        "price_per_day": "700.00",
        "quantity": 1,
    }


@pytest.mark.asyncio
async def test_owner_creates_own_equipment(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    me = await client.get("/auth/me", headers=headers)
    owner_id = me.json()["id"]

    response = await client.post("/owner/equipment", json=payload(), headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["owner_id"] == owner_id


@pytest.mark.asyncio
async def test_client_cannot_use_owner_api(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    assert (await client.get("/owner/equipment", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_owner_sees_only_own_equipment(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    me = await client.get("/auth/me", headers=headers)
    owner_id = me.json()["id"]

    await create_equipment(db_session, title="Моя позиция", owner_id=owner_id)
    await create_equipment(db_session, title="Чужая позиция")

    response = await client.get("/owner/equipment", headers=headers)
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Моя позиция"


@pytest.mark.asyncio
async def test_owner_cannot_edit_foreign_equipment(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    foreign = await create_equipment(db_session, title="Чужая")

    response = await client.patch(
        f"/owner/equipment/{foreign.id}", json={"title": "Взлом"}, headers=headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_edits_any_equipment(client: AsyncClient, db_session: AsyncSession):
    admin_headers = await auth_headers(client, db_session, admin=True)
    foreign = await create_equipment(db_session)

    response = await client.patch(
        f"/owner/equipment/{foreign.id}", json={"title": "Обновлено"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Обновлено"


@pytest.mark.asyncio
async def test_delete_blocked_by_active_booking(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner_headers = await auth_headers(client, db_session, role=UserRole.owner)
    me = await client.get("/auth/me", headers=owner_headers)
    item = await create_equipment(db_session, owner_id=me.json()["id"], price_per_hour="100.00")

    start = (datetime.now(UTC) + timedelta(hours=2)).replace(second=0, microsecond=0)
    booking = await client.post(
        "/bookings",
        json={
            "equipment_id": item.id,
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=3)).isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
        headers=client_headers,
    )
    assert booking.status_code == 201, booking.text

    blocked = await client.delete(f"/owner/equipment/{item.id}", headers=owner_headers)
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_owner_bookings_and_stats(client: AsyncClient, db_session: AsyncSession):
    client_headers = await auth_headers(client, db_session)
    owner_headers = await auth_headers(client, db_session, role=UserRole.owner)
    me = await client.get("/auth/me", headers=owner_headers)
    item = await create_equipment(db_session, owner_id=me.json()["id"], price_per_hour="100.00")
    await create_equipment(db_session, title="Чужая", price_per_hour="100.00")

    start = (datetime.now(UTC) + timedelta(hours=2)).replace(second=0, microsecond=0)
    created = await client.post(
        "/bookings",
        json={
            "equipment_id": item.id,
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=3)).isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
        headers=client_headers,
    )
    assert created.status_code == 201, created.text

    bookings = await client.get("/owner/bookings", headers=owner_headers)
    assert bookings.status_code == 200
    assert bookings.json()["total"] == 1

    stats = await client.get("/owner/stats", headers=owner_headers)
    data = stats.json()
    assert data["equipment_total"] == 1
    assert data["bookings_total"] == 1
    assert data["bookings_active"] == 1


@pytest.mark.asyncio
async def test_admin_users_list_and_patch(client: AsyncClient, db_session: AsyncSession):
    await auth_headers(client, db_session)
    admin_headers = await auth_headers(client, db_session, admin=True)

    listing = await client.get("/admin/users?q=user@", headers=admin_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    user_id = listing.json()["items"][0]["id"]

    promoted = await client.patch(
        f"/admin/users/{user_id}", json={"role": "owner"}, headers=admin_headers
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "owner"

    flagged = await client.patch(
        f"/admin/users/{user_id}", json={"is_abuser": True}, headers=admin_headers
    )
    assert flagged.json()["is_abuser"] is True


@pytest.mark.asyncio
async def test_admin_cannot_demote_self(client: AsyncClient, db_session: AsyncSession):
    admin_headers = await auth_headers(client, db_session, admin=True)
    me = await client.get("/auth/me", headers=admin_headers)

    response = await client.patch(
        f"/admin/users/{me.json()['id']}", json={"role": "user"}, headers=admin_headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_stats(client: AsyncClient, db_session: AsyncSession):
    admin_headers = await auth_headers(client, db_session, admin=True)
    await create_equipment(db_session)

    response = await client.get("/admin/stats", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["users"] >= 1
    assert data["equipment"] == 1


@pytest.mark.asyncio
async def test_owner_stats_isolated(client: AsyncClient, db_session: AsyncSession):
    owner_one = await create_user(db_session, email="owner1@example.com", role=UserRole.owner)
    await create_user(db_session, email="owner2@example.com", role=UserRole.owner)
    await create_equipment(db_session, title="Первая", owner_id=owner_one.id)

    token = await login(client, "owner2@example.com", "secret123")
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/owner/stats", headers=headers)
    assert response.json()["equipment_total"] == 0
