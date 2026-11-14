import asyncio
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_image(data: bytes, content_type: str | None) -> None:
    if content_type not in ALLOWED_MIME:
        raise ValueError("Поддерживаются только JPEG, PNG и WebP")
    if len(data) > settings.max_image_mb * 1024 * 1024:
        raise ValueError(f"Файл больше {settings.max_image_mb} МБ")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise ValueError("Неизвестный формат изображения")
            probe.verify()
    except UnidentifiedImageError as exc:
        raise ValueError("Файл не является изображением") from exc


def _prepare(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def _process_and_save(equipment_id: int, data: bytes) -> dict:
    with Image.open(io.BytesIO(data)) as source:
        source.load()
        image = _prepare(source)

    folder = Path(settings.uploads_dir) / str(equipment_id)
    folder.mkdir(parents=True, exist_ok=True)

    full_name = f"{uuid.uuid4().hex}.webp"
    thumb_name = f"{uuid.uuid4().hex}_thumb.webp"

    full = image.copy()
    full.thumbnail((settings.image_max_side, settings.image_max_side))
    full.save(folder / full_name, "WEBP", quality=85, method=6)

    thumb = image.copy()
    thumb.thumbnail((settings.thumb_max_side, settings.thumb_max_side))
    thumb.save(folder / thumb_name, "WEBP", quality=80, method=6)

    return {
        "filename": full_name,
        "thumb_filename": thumb_name,
        "width": full.width,
        "height": full.height,
        "size_bytes": (folder / full_name).stat().st_size,
    }


async def save_image(equipment_id: int, data: bytes) -> dict:
    return await asyncio.to_thread(_process_and_save, equipment_id, data)


def delete_files(equipment_id: int, filenames: list[str]) -> None:
    folder = Path(settings.uploads_dir) / str(equipment_id)
    for name in filenames:
        try:
            (folder / name).unlink(missing_ok=True)
        except OSError:
            continue
