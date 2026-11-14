from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_owner
from app.core.config import settings
from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.equipment_image import EquipmentImage
from app.models.user import User
from app.schemas.image import EquipmentImageRead
from app.services import equipment_service, image_service

router = APIRouter(tags=["images"])


def _to_read(image: EquipmentImage) -> EquipmentImageRead:
    base = f"/media/{image.equipment_id}"
    return EquipmentImageRead(
        id=image.id,
        url=f"{base}/{image.filename}",
        thumb_url=f"{base}/{image.thumb_filename}",
        is_primary=image.is_primary,
        width=image.width,
        height=image.height,
        size_bytes=image.size_bytes,
    )


def _require_access(item: Equipment, user: User) -> None:
    if not user.is_admin and item.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Можно изменять только свои позиции")


async def _load_equipment(db: AsyncSession, equipment_id: int) -> Equipment:
    item = await equipment_service.get_equipment(db, equipment_id, include_inactive=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Оборудование не найдено")
    return item


@router.get("/equipment/{equipment_id}/images", response_model=list[EquipmentImageRead])
async def list_images(
    equipment_id: int, db: AsyncSession = Depends(get_db)
) -> list[EquipmentImageRead]:
    stmt = (
        select(EquipmentImage)
        .where(EquipmentImage.equipment_id == equipment_id)
        .order_by(EquipmentImage.is_primary.desc(), EquipmentImage.sort_order, EquipmentImage.id)
    )
    return [_to_read(image) for image in (await db.scalars(stmt)).all()]


@router.post(
    "/owner/equipment/{equipment_id}/images",
    response_model=EquipmentImageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    equipment_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> EquipmentImageRead:
    item = await _load_equipment(db, equipment_id)
    _require_access(item, user)

    count = await db.scalar(
        select(func.count())
        .select_from(EquipmentImage)
        .where(EquipmentImage.equipment_id == equipment_id)
    )
    if int(count or 0) >= settings.max_images_per_equipment:
        raise HTTPException(
            status_code=409,
            detail=f"Максимум {settings.max_images_per_equipment} изображений на позицию",
        )

    data = await file.read()
    try:
        image_service.validate_image(data, file.content_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    processed = await image_service.save_image(equipment_id, data)

    is_primary = int(count or 0) == 0
    image = EquipmentImage(
        equipment_id=equipment_id,
        is_primary=is_primary,
        sort_order=int(count or 0),
        **processed,
    )
    db.add(image)
    if is_primary:
        item.cover_url = f"/media/{equipment_id}/{processed['thumb_filename']}"
    await db.commit()
    await db.refresh(image)
    return _to_read(image)


@router.delete(
    "/owner/equipment/{equipment_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_image(
    equipment_id: int,
    image_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> None:
    item = await _load_equipment(db, equipment_id)
    _require_access(item, user)

    image = await db.get(EquipmentImage, image_id)
    if image is None or image.equipment_id != equipment_id:
        raise HTTPException(status_code=404, detail="Изображение не найдено")

    was_primary = image.is_primary
    filenames = [image.filename, image.thumb_filename]
    await db.delete(image)
    await db.flush()

    if was_primary:
        replacement = await db.scalar(
            select(EquipmentImage)
            .where(EquipmentImage.equipment_id == equipment_id)
            .order_by(EquipmentImage.sort_order, EquipmentImage.id)
            .limit(1)
        )
        if replacement is not None:
            replacement.is_primary = True
            item.cover_url = f"/media/{equipment_id}/{replacement.thumb_filename}"
        else:
            item.cover_url = ""

    await db.commit()
    image_service.delete_files(equipment_id, filenames)


@router.patch(
    "/owner/equipment/{equipment_id}/images/{image_id}/primary",
    response_model=EquipmentImageRead,
)
async def set_primary(
    equipment_id: int,
    image_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_owner),
) -> EquipmentImageRead:
    item = await _load_equipment(db, equipment_id)
    _require_access(item, user)

    images = list(
        (
            await db.scalars(
                select(EquipmentImage).where(EquipmentImage.equipment_id == equipment_id)
            )
        ).all()
    )
    target = next((image for image in images if image.id == image_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Изображение не найдено")

    for image in images:
        image.is_primary = image.id == image_id
    item.cover_url = f"/media/{equipment_id}/{target.thumb_filename}"
    await db.commit()
    await db.refresh(target)
    return _to_read(target)
