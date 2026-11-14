import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://rental:rental@localhost:5432/rental_test"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SMTP_HOST"] = ""
os.environ["EMAIL_DEBUG_RETURN_TOKEN"] = "true"

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models
from app.db.base import Base
from app.db.session import get_db
from app.main import app

ADMIN_DSN = "postgresql://rental:rental@localhost:5432/postgres"
TEST_URL = "postgresql+asyncpg://rental:rental@localhost:5432/rental_test"
TEST_DB = "rental_test"


@pytest_asyncio.fixture(scope="session")
async def engine():
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()

    eng = create_async_engine(TEST_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(engine):
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def client(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
