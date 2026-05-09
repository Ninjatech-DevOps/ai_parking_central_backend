import uuid
from typing import Optional

from src.app.schemas.base import BaseSchema, BaseResponse


class FloorCreate(BaseSchema):
    location_id: uuid.UUID
    label: str
    level_number: int = 0
    capacity: int = 0


class FloorUpdate(BaseSchema):
    label: Optional[str] = None
    level_number: Optional[int] = None
    capacity: Optional[int] = None


class FloorResponse(BaseResponse):
    location_id: uuid.UUID
    label: str
    level_number: int
    capacity: int


class FloorFilter(BaseSchema):
    location_id: Optional[uuid.UUID] = None
