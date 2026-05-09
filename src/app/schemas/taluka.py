import uuid
from typing import Optional

from src.app.schemas.base import BaseSchema, BaseResponse


class TalukaCreate(BaseSchema):
    name: str
    city_id: uuid.UUID


class TalukaUpdate(BaseSchema):
    name: Optional[str] = None


class TalukaResponse(BaseResponse):
    name: str
    city_id: uuid.UUID


class TalukaFilter(BaseSchema):
    city_id: Optional[uuid.UUID] = None
