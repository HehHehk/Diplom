from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from tests.helpers import create_user, login

LONG_TEXT = (
    "Во время аренды оборудование перестало работать: сломался механизм, "
    "прошу рассмотреть возврат и компенсацию"
)


def soon(hours: int = 1) -> datetime:
    return (datetime.now(UTC) + timedelta(hours=hours)).replace(second=0, microsecond=0)


@pytest.mark.asyncio
async def test_full_rental_cycle(client: AsyncClient, db_session: AsyncSession):
    owner = await create_user(db_session, email="owner@example.com", role=UserRole.owner)
    renter = await create_user(db_session, email="user@example.com")
    await create_user(db_session, email="admin@example.com", role=UserRole.admin)

    owner_headers = {"Authorization": f"Bearer {await login(client, owner.email, 'secret123')}"}
    client_headers = {"Authorization": f"Bearer {await login(client, renter.email, 'secret123')}"}
    admin_headers = {
        "Authorization": f"Bearer {await login(client, 'admin@example.com', 'secret123')}"
    }

    # 1. Арендодатель создаёт позицию
    created = await client.post(
        "/owner/equipment",
        headers=owner_headers,
        json={
            "title": "E2E велосипед",
            "category": "Велосипеды",
            "brand": "E2E",
            "price_per_hour": "300.00",
            "price_per_day": "1200.00",
            "min_hours": 1,
            "max_hours": 24,
            "quantity": 1,
            "working_hours": None,
        },
    )
    assert created.status_code == 201, created.text
    equipment_id = created.json()["id"]

    # 2. Клиент видит цену и бронирует
    start, end = soon(1), soon(3)
    preview = await client.post(
        "/bookings/preview",
        headers=client_headers,
        json={
            "equipment_id": equipment_id,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["recommended"] == "hour"
    assert preview.json()["options"][0]["total"] == "600.00"

    booking = await client.post(
        "/bookings",
        headers=client_headers,
        json={
            "equipment_id": equipment_id,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
    )
    assert booking.status_code == 201, booking.text
    booking_id = booking.json()["id"]

    # 3. Арендодатель выдаёт оборудование
    pickup = await client.post(f"/bookings/{booking_id}/pickup", headers=owner_headers)
    assert pickup.status_code == 200, pickup.text
    assert pickup.json()["picked_up_at"] is not None

    # 4. Клиент сообщает о поломке — спор уходит админу
    returned = await client.post(
        f"/bookings/{booking_id}/early-return",
        headers=client_headers,
        json={"reason": "equipment_broken", "description": LONG_TEXT},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "terminated"
    assert returned.json()["dispute_status"] == "pending"

    # 5. Админ решает спор
    queue = await client.get("/admin/disputes", headers=admin_headers)
    assert queue.json()["total"] == 1
    resolved = await client.post(
        f"/admin/disputes/{booking_id}/resolve",
        headers=admin_headers,
        json={"outcome": "equipment_fault", "comment": "Подтверждено, неисправность оборудования"},
    )
    assert resolved.status_code == 200, resolved.text
    decision = resolved.json()
    assert decision["outcome"] == "equipment_fault"
    assert float(decision["refund_amount"]) == 600.0
    assert float(decision["compensation_amount"]) == 60.0

    # 6. Повторная аренда: выдача и обычный возврат арендодателем
    second = await client.post(
        "/bookings",
        headers=client_headers,
        json={
            "equipment_id": equipment_id,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "quantity": 1,
            "billing_unit": "hour",
        },
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]
    await client.post(f"/bookings/{second_id}/pickup", headers=owner_headers)
    returned_second = await client.post(
        f"/bookings/{second_id}/return", headers=owner_headers, json={}
    )
    assert returned_second.status_code == 200, returned_second.text
    assert returned_second.json()["status"] == "terminated"

    # 7. Контрольные точки
    final = await client.get(f"/bookings/{booking_id}", headers=admin_headers)
    assert final.json()["dispute_status"] == "resolved"

    stats = await client.get("/owner/stats", headers=owner_headers)
    assert stats.json()["equipment_total"] == 1
    assert stats.json()["bookings_total"] == 2
    assert stats.json()["disputes_pending"] == 0

    admin_stats = await client.get("/admin/stats", headers=admin_headers)
    assert admin_stats.json()["disputes_pending"] == 0
