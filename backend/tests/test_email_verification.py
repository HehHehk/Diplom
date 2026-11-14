import pytest
from httpx import AsyncClient

REGISTER = "/auth/register"
LOGIN = "/auth/login"


def payload(email: str = "verify@example.com") -> dict:
    return {"email": email, "password": "secret123", "full_name": "Verify User"}


@pytest.mark.asyncio
async def test_registration_requires_email_confirmation(client: AsyncClient):
    created = await client.post(REGISTER, json=payload())
    assert created.status_code == 201, created.text
    token = created.headers.get("x-debug-verification-token")
    assert token, "в dev-режиме токен должен возвращаться в заголовке"

    blocked = await client.post(
        LOGIN, data={"username": "verify@example.com", "password": "secret123"}
    )
    assert blocked.status_code == 403
    assert "Подтвердите email" in blocked.json()["detail"]

    verified = await client.post("/auth/verify-email", json={"token": token})
    assert verified.status_code == 200, verified.text
    assert verified.json()["email_verified_at"] is not None

    allowed = await client.post(
        LOGIN, data={"username": "verify@example.com", "password": "secret123"}
    )
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_invalid_verification_token(client: AsyncClient):
    response = await client.post("/auth/verify-email", json={"token": "invalid-token-value"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_resend_rotates_token(client: AsyncClient):
    created = await client.post(REGISTER, json=payload("resend@example.com"))
    old_token = created.headers["x-debug-verification-token"]

    resent = await client.post("/auth/resend-verification", json={"email": "resend@example.com"})
    assert resent.status_code == 202
    new_token = resent.headers.get("x-debug-verification-token")
    assert new_token and new_token != old_token

    assert (await client.post("/auth/verify-email", json={"token": old_token})).status_code == 400
    assert (await client.post("/auth/verify-email", json={"token": new_token})).status_code == 200


@pytest.mark.asyncio
async def test_resend_unknown_email_is_silent(client: AsyncClient):
    response = await client.post("/auth/resend-verification", json={"email": "nobody@example.com"})
    assert response.status_code == 202
