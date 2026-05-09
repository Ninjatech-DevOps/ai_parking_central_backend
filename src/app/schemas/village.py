import uuid
from typing import Optional

from src.app.schemas.base import BaseSchema, BaseResponse


class VillageCreate(BaseSchema):
    name: str
    taluka_id: uuid.UUID


class VillageUpdate(BaseSchema):
    name: Optional[str] = None


class VillageResponse(BaseResponse):
    name: str
    taluka_id: uuid.UUID


class VillageFilter(BaseSchema):
    taluka_id: Optional[uuid.UUID] = None
