import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import admin, auth, bookings, equipment
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.services import booking_service, dispute_service

logger = logging.getLogger("app.no_show")


async def _no_show_worker() -> None:
    """Периодически фиксирует неявки, у которых истекло адаптивное окно."""
    while True:
        try:
            async with SessionLocal() as db:
                count = await booking_service.apply_due_no_shows(db)
                if count:
                    logger.info("Зафиксировано неявок: %s", count)
                resolved = await dispute_service.apply_dispute_sla(db)
                if resolved:
                    logger.info("Споров закрыто по SLA: %s", resolved)
        except Exception:
            logger.exception("Ошибка обработки неявок")
        await asyncio.sleep(settings.no_show_scheduler_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task: asyncio.Task | None = None
    if settings.no_show_scheduler_enabled:
        task = asyncio.create_task(_no_show_worker())
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="API для аренды оборудования с интеллектуальным бронированием",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(equipment.router)
    app.include_router(bookings.router)
    app.include_router(admin.router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
