import uuid
from typing import Optional

from src.app.schemas.base import BaseSchema, BaseResponse


class ZoneCreate(BaseSchema):
    name: str
    floor_id: uuid.UUID
    capacity: int = 0


class ZoneUpdate(BaseSchema):
    name: Optional[str] = None
    capacity: Optional[int] = None


class ZoneResponse(BaseResponse):
    name: str
    floor_id: uuid.UUID
    capacity: int


class ZoneFilter(BaseSchema):
    floor_id: Optional[uuid.UUID] = None
