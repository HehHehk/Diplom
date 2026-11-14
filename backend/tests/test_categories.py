import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from tests.helpers import auth_headers


@pytest.mark.asyncio
async def test_owner_creates_category(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    created = await client.post("/categories", json={"name": "Электроинструмент"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Электроинструмент"

    listing = await client.get("/categories")
    assert any(item["name"] == "Электроинструмент" for item in listing.json())

    duplicate = await client.post(
        "/categories", json={"name": "Электроинструмент"}, headers=headers
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_client_cannot_create_category(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    response = await client.post("/categories", json={"name": "Скрытая"}, headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_equipment_registers_new_category(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    created = await client.post(
        "/owner/equipment",
        json={
            "title": "Категорийный тест",
            "category": "Новая категория",
            "price_per_hour": "10.00",
            "quantity": 1,
            "working_hours": None,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    listing = await client.get("/categories")
    names = [item["name"] for item in listing.json()]
    assert "Новая категория" in names
