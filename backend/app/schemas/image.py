from pydantic import BaseModel


class EquipmentImageRead(BaseModel):
    id: int
    url: str
    thumb_url: str
    is_primary: bool
    width: int
    height: int
    size_bytes: int
