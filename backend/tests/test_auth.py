import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import auth_headers, create_user, login

REGISTER = "/auth/register"
LOGIN = "/auth/login"


@pytest.mark.asyncio
async def test_register_returns_user(client: AsyncClient):
    response = await client.post(
        REGISTER,
        json={"email": "new@example.com", "password": "secret123", "full_name": "Новый"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new@example.com"
    assert data["role"] == "user"
    assert "hashed_password" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "secret123", "full_name": "A"}
    assert (await client.post(REGISTER, json=payload)).status_code == 201
    assert (await client.post(REGISTER, json=payload)).status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    response = await client.post(
        REGISTER, json={"email": "not-an-email", "password": "secret123", "full_name": "A"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    response = await client.post(
        REGISTER, json={"email": "short@example.com", "password": "123", "full_name": "A"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_password_without_digit(client: AsyncClient):
    response = await client.post(
        REGISTER,
        json={"email": "nodigit@example.com", "password": "abcdefghi", "full_name": "A"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_common_password(client: AsyncClient):
    response = await client.post(
        REGISTER,
        json={"email": "common@example.com", "password": "qwerty123", "full_name": "A"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_strong_password(client: AsyncClient):
    response = await client.post(
        REGISTER,
        json={"email": "strong@example.com", "password": "StrongPass1!", "full_name": "A"},
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_login_success_and_me(client: AsyncClient, db_session: AsyncSession):
    await create_user(db_session)
    token = await login(client, "user@example.com", "secret123")

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db_session: AsyncSession):
    await create_user(db_session)
    response = await client.post(
        LOGIN, data={"username": "user@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient):
    response = await client.post(
        LOGIN, data={"username": "nobody@example.com", "password": "secret123"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_token(client: AsyncClient):
    assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_garbage_token(client: AsyncClient):
    response = await client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_create_equipment(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session, admin=True)
    response = await client.post(
        "/equipment",
        headers=headers,
        json={
            "title": "Перфоратор",
            "category": "Инструмент",
            "brand": "Bosch",
            "price_per_day": "500.00",
            "quantity": 2,
            "specs": {"power_w": 800},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "Перфоратор"


@pytest.mark.asyncio
async def test_regular_user_cannot_create_equipment(client: AsyncClient, db_session: AsyncSession):
    headers = await auth_headers(client, db_session)
    response = await client.post(
        "/equipment",
        headers=headers,
        json={"title": "X", "category": "Y", "price_per_day": "1.00"},
    )
    assert response.status_code == 403
