import math
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user, get_optional_user
from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.user import User
from app.schemas.booking import AvailabilityResponse, BusyInterval
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentPage,
    EquipmentRead,
    EquipmentRecommendation,
    EquipmentUpdate,
    RecommendationList,
)
from app.schemas.forecast import LoadForecast
from app.services import booking_service, equipment_service, forecast_service, recommender

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("/categories", response_model=list[str])
async def categories(db: AsyncSession = Depends(get_db)) -> list[str]:
    """Список категорий для фильтров каталога."""
    return await equipment_service.list_categories(db)


@router.get("", response_model=EquipmentPage)
async def list_equipment(
    q: str | None = Query(default=None, description="Поиск по названию, бренду, категории"),
    category: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    sort: Literal["newest", "price_asc", "price_desc", "title"] = "newest",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> EquipmentPage:
    """Каталог оборудования с пагинацией, фильтрами и поиском."""
    show_inactive = include_inactive and user is not None and user.is_admin
    items, total = await equipment_service.list_equipment(
        db,
        q=q,
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        include_inactive=show_inactive,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return EquipmentPage(
        items=[EquipmentRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        pages=math.ceil(total / limit) if limit else 0,
    )


def _recommendation(item: Equipment, score: float) -> EquipmentRecommendation:
    base = EquipmentRead.model_validate(item).model_dump()
    return EquipmentRecommendation(**base, score=float(score))


@router.get("/popular", response_model=RecommendationList)
async def popular(
    limit: int = Query(default=6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> RecommendationList:
    """Популярные позиции за 30 дней: брони и просмотры."""
    pairs = await recommender.popular_equipment(db, limit)
    return RecommendationList(
        strategy="popular",
        items=[_recommendation(item, score) for item, score in pairs],
    )


@router.get("/{equipment_id}", response_model=EquipmentRead)
async def get_equipment(
    equipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> Equipment:
    """Карточка оборудования. Просмотр фиксируется в `interactions`."""
    item = await equipment_service.get_equipment(db, equipment_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Оборудование не найдено")
    if user is None or (not user.is_admin and item.owner_id != user.id):
        await equipment_service.log_view(db, item.id, user.id if user else None)
    return item


@router.get("/{equipment_id}/availability", response_model=AvailabilityResponse)
async def availability(
    equipment_id: int,
    from_at: AwareDatetime = Query(alias="from"),
    to_at: AwareDatetime = Query(alias="to"),
    db: AsyncSession = Depends(get_db),
) -> AvailabilityResponse:
    """Занятые интервалы оборудования за период — для календаря бронирования."""
    item = await equipment_service.get_equipment(db, equipment_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Оборудование не найдено")
    if to_at <= from_at:
        raise HTTPException(status_code=422, detail="Параметр to должен быть позже from")

    bookings = await booking_service.busy_intervals(db, item.id, from_at, to_at)
    buffer = timedelta(minutes=item.buffer_minutes)
    return AvailabilityResponse(
        equipment_id=item.id,
        quantity=item.quantity,
        timezone=item.timezone,
        buffer_minutes=item.buffer_minutes,
        from_at=from_at,
        to_at=to_at,
        busy=[
            BusyInterval(
                start_at=min(b.start_at, b.picked_up_at or b.start_at) - buffer,
                end_at=b.end_at + buffer,
                quantity=b.quantity,
            )
            for b in bookings
        ],
    )


@router.get("/{equipment_id}/recommendations", response_model=RecommendationList)
async def recommendations(
    equipment_id: int,
    limit: int = Query(default=6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> RecommendationList:
    """Похожие позиции. При отсутствии сходства — блок «популярное»."""
    item = await equipment_service.get_equipment(db, equipment_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Оборудование не найдено")

    strategy, pairs = await recommender.for_equipment(db, item, limit)
    return RecommendationList(
        strategy=strategy,
        items=[_recommendation(entry, score) for entry, score in pairs],
    )


@router.get("/{equipment_id}/load-forecast", response_model=LoadForecast)
async def load_forecast(
    equipment_id: int,
    days: int = Query(default=90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> LoadForecast:
    """Прогноз загрузки по фактическим выдачам: дни недели и часы."""
    item = await equipment_service.get_equipment(db, equipment_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Оборудование не найдено")
    return LoadForecast(**await forecast_service.load_forecast(db, item, days))


@router.post("", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    data: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Equipment:
    payload = data.model_dump()
    owner_id = payload.pop("owner_id")
    if owner_id is not None and admin.is_admin:
        await equipment_service.resolve_owner(db, owner_id)
    else:
        owner_id = admin.id
    item = Equipment(**payload, owner_id=owner_id)
    equipment_service.validate_state(item)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/{equipment_id}", response_model=EquipmentRead)
async def update_equipment(
    equipment_id: int,
    data: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Equipment:
    item = await equipment_service.get_equipment(db, equipment_id, include_inactive=True)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Оборудование не найдено")
    if not user.is_admin and item.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Можно редактировать только свои позиции"
        )

    changes = data.model_dump(exclude_unset=True)
    if not user.is_admin:
        changes.pop("owner_id", None)
    elif changes.get("owner_id") is not None:
        await equipment_service.resolve_owner(db, changes["owner_id"])

    for field, value in changes.items():
        setattr(item, field, value)

    equipment_service.validate_state(item)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    equipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Мягкое удаление: позиция скрывается из каталога, история сохраняется."""
    item = await equipment_service.get_equipment(db, equipment_id, include_inactive=True)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Оборудование не найдено")
    if not user.is_admin and item.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Можно удалять только свои позиции"
        )
    if await equipment_service.has_active_bookings(db, item.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="По позиции есть активные брони — сначала завершите их",
        )
    item.is_active = False
    await db.commit()
