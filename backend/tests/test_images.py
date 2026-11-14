import io

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from tests.helpers import auth_headers


def image_bytes(color: str = "red", size: tuple[int, int] = (300, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


async def create_item(client: AsyncClient, headers: dict[str, str]) -> int:
    response = await client.post(
        "/owner/equipment",
        json={
            "title": "Позиция с фото",
            "category": "Фототест",
            "price_per_hour": "10.00",
            "quantity": 1,
            "working_hours": None,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def upload(client: AsyncClient, headers: dict[str, str], equipment_id: int, data=None):
    return await client.post(
        f"/owner/equipment/{equipment_id}/images",
        files={"file": ("photo.png", data or image_bytes(), "image/png")},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_upload_and_cover(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    equipment_id = await create_item(client, headers)

    first = await upload(client, headers, equipment_id)
    assert first.status_code == 201, first.text
    data = first.json()
    assert data["is_primary"] is True
    assert data["url"].endswith(".webp")
    assert data["thumb_url"].endswith("_thumb.webp")

    item = await client.get(f"/equipment/{equipment_id}")
    assert item.json()["cover_url"].endswith("_thumb.webp")

    served = await client.get(data["url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"

    second = await upload(client, headers, equipment_id, image_bytes("blue"))
    assert second.status_code == 201
    assert second.json()["is_primary"] is False

    listing = await client.get(f"/equipment/{equipment_id}/images")
    assert len(listing.json()) == 2
    assert listing.json()[0]["is_primary"] is True


@pytest.mark.asyncio
async def test_set_primary(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    equipment_id = await create_item(client, headers)
    first = (await upload(client, headers, equipment_id)).json()
    second = (await upload(client, headers, equipment_id, image_bytes("green"))).json()

    response = await client.patch(
        f"/owner/equipment/{equipment_id}/images/{second['id']}/primary", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_primary"] is True

    listing = (await client.get(f"/equipment/{equipment_id}/images")).json()
    assert listing[0]["id"] == second["id"]
    assert listing[0]["is_primary"] is True
    assert first["id"] != second["id"]


@pytest.mark.asyncio
async def test_delete_primary_promotes_next(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    equipment_id = await create_item(client, headers)
    first = (await upload(client, headers, equipment_id)).json()
    second = (await upload(client, headers, equipment_id, image_bytes("yellow"))).json()

    response = await client.delete(
        f"/owner/equipment/{equipment_id}/images/{first['id']}", headers=headers
    )
    assert response.status_code == 204

    listing = (await client.get(f"/equipment/{equipment_id}/images")).json()
    assert len(listing) == 1
    assert listing[0]["id"] == second["id"]
    assert listing[0]["is_primary"] is True


@pytest.mark.asyncio
async def test_image_limit(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    equipment_id = await create_item(client, headers)
    for _ in range(5):
        assert (await upload(client, headers, equipment_id)).status_code == 201
    sixth = await upload(client, headers, equipment_id)
    assert sixth.status_code == 409


@pytest.mark.asyncio
async def test_rejects_non_image(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, role=UserRole.owner)
    equipment_id = await create_item(client, headers)
    response = await upload(client, headers, equipment_id, b"not an image")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_client_cannot_upload(client: AsyncClient, db_session: AsyncSession):
    owner_headers = await auth_headers(client, db_session, role=UserRole.owner)
    equipment_id = await create_item(client, owner_headers)
    client_headers = await auth_headers(client, db_session)
    response = await upload(client, client_headers, equipment_id)
    assert response.status_code == 403
