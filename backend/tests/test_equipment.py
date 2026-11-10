import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import Interaction
from tests.helpers import auth_headers, create_equipment


@pytest.mark.asyncio
async def test_catalog_empty(client: AsyncClient):
    response = await client.get("/equipment")
    assert response.status_code == 200
    data = response.json()
    assert data == {"items": [], "total": 0, "limit": 20, "offset": 0, "pages": 0}


@pytest.mark.asyncio
async def test_catalog_pagination(client: AsyncClient, db_session: AsyncSession):
    for i in range(7):
        await create_equipment(db_session, title=f"Позиция {i}")

    response = await client.get("/equipment", params={"limit": 3, "offset": 6})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 7
    assert data["pages"] == 3
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_catalog_search(client: AsyncClient, db_session: AsyncSession):
    await create_equipment(db_session, title="Перфоратор Bosch")
    await create_equipment(db_session, title="Бензопила Stihl", brand="Stihl")

    response = await client.get("/equipment", params={"q": "bosch"})
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["brand"] == "Bosch"


@pytest.mark.asyncio
async def test_catalog_filters(client: AsyncClient, db_session: AsyncSession):
    await create_equipment(db_session, title="A", category="Инструмент", price="100.00")
    await create_equipment(db_session, title="B", category="Инструмент", price="900.00")
    await create_equipment(db_session, title="C", category="Сад", price="500.00")

    by_category = (await client.get("/equipment", params={"category": "Инструмент"})).json()
    assert by_category["total"] == 2

    by_price = (await client.get("/equipment", params={"min_price": 400, "max_price": 1000})).json()
    assert by_price["total"] == 2

    combined = (
        await client.get("/equipment", params={"category": "Инструмент", "max_price": 500})
    ).json()
    assert combined["total"] == 1
    assert combined["items"][0]["title"] == "A"


@pytest.mark.asyncio
async def test_catalog_sort_by_price(client: AsyncClient, db_session: AsyncSession):
    await create_equipment(db_session, title="Mid", price="500.00")
    await create_equipment(db_session, title="Cheap", price="100.00")
    await create_equipment(db_session, title="Pricey", price="900.00")

    ascending = (await client.get("/equipment", params={"sort": "price_asc"})).json()
    assert [i["title"] for i in ascending["items"]] == ["Cheap", "Mid", "Pricey"]

    descending = (await client.get("/equipment", params={"sort": "price_desc"})).json()
    assert [i["title"] for i in descending["items"]] == ["Pricey", "Mid", "Cheap"]


@pytest.mark.asyncio
async def test_categories(client: AsyncClient, db_session: AsyncSession):
    await create_equipment(db_session, title="A", category="Инструмент")
    await create_equipment(db_session, title="B", category="Сад")
    await create_equipment(db_session, title="C", category="Сад")

    response = await client.get("/equipment/categories")
    assert response.status_code == 200
    assert sorted(response.json()) == ["Инструмент", "Сад"]


@pytest.mark.asyncio
async def test_detail_logs_interaction(client: AsyncClient, db_session: AsyncSession):
    item = await create_equipment(db_session)

    before = await db_session.scalar(select(func.count()).select_from(Interaction))
    response = await client.get(f"/equipment/{item.id}")
    after = await db_session.scalar(select(func.count()).select_from(Interaction))

    assert response.status_code == 200
    assert response.json()["id"] == item.id
    assert after == before + 1


@pytest.mark.asyncio
async def test_detail_logs_authorized_view(client: AsyncClient, db_session: AsyncSession):
    item = await create_equipment(db_session)
    headers = await auth_headers(client, db_session)

    await client.get(f"/equipment/{item.id}", headers=headers)

    interaction = await db_session.scalar(select(Interaction))
    assert interaction is not None
    assert interaction.user_id is not None
    assert interaction.equipment_id == item.id


@pytest.mark.asyncio
async def test_detail_not_found(client: AsyncClient):
    response = await client.get("/equipment/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_soft_deleted_hidden_from_catalog(client: AsyncClient, db_session: AsyncSession):
    item = await create_equipment(db_session)
    headers = await auth_headers(client, db_session, admin=True)

    assert (await client.delete(f"/equipment/{item.id}", headers=headers)).status_code == 204

    public = (await client.get("/equipment")).json()
    assert public["total"] == 0
    assert (await client.get(f"/equipment/{item.id}")).status_code == 404

    admin_view = (
        await client.get("/equipment", params={"include_inactive": True}, headers=headers)
    ).json()
    assert admin_view["total"] == 1
