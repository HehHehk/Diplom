from datetime import UTC, datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.equipment import Equipment
from app.models.user import User


async def create_user(
    db: AsyncSession,
    *,
    email: str = "user@example.com",
    password: str = "secret123",
    role: UserRole = UserRole.user,
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name="Test User",
        role=role,
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def auth_headers(
    client: AsyncClient, db: AsyncSession, *, admin: bool = False, role: UserRole | None = None
) -> dict[str, str]:
    if admin:
        role = UserRole.admin
    role = role or UserRole.user
    email = {
        UserRole.admin: "admin@example.com",
        UserRole.owner: "owner@example.com",
        UserRole.user: "user@example.com",
    }[role]
    await create_user(db, email=email, role=role)
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def create_equipment(
    db: AsyncSession,
    *,
    title: str = "Перфоратор Bosch",
    category: str = "Инструмент",
    brand: str = "Bosch",
    price_per_day: str | None = "500.00",
    price_per_hour: str | None = None,
    min_hours: int = 1,
    min_days: int = 1,
    max_hours: int = 24,
    max_days: int = 30,
    quantity: int = 1,
    buffer_minutes: int = 30,
    lead_time_minutes: int = 30,
    working_hours: dict | None = None,
    timezone: str = "Europe/Moscow",
    owner_id: int | None = None,
    specs: dict | None = None,
) -> Equipment:
    item = Equipment(
        owner_id=owner_id,
        title=title,
        category=category,
        brand=brand,
        price_per_day=Decimal(price_per_day) if price_per_day is not None else None,
        price_per_hour=Decimal(price_per_hour) if price_per_hour is not None else None,
        min_hours=min_hours,
        min_days=min_days,
        max_hours=max_hours,
        max_days=max_days,
        quantity=quantity,
        buffer_minutes=buffer_minutes,
        lead_time_minutes=lead_time_minutes,
        working_hours=working_hours,
        timezone=timezone,
        specs=specs or {},
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
