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
    client: AsyncClient, db: AsyncSession, *, admin: bool = False
) -> dict[str, str]:
    email = "admin@example.com" if admin else "user@example.com"
    await create_user(db, email=email, role=UserRole.admin if admin else UserRole.user)
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def create_equipment(
    db: AsyncSession,
    *,
    title: str = "Перфоратор Bosch",
    category: str = "Инструмент",
    brand: str = "Bosch",
    price: str = "500.00",
    quantity: int = 2,
    specs: dict | None = None,
) -> Equipment:
    item = Equipment(
        title=title,
        category=category,
        brand=brand,
        price_per_day=Decimal(price),
        quantity=quantity,
        specs=specs or {},
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
