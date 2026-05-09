import uuid
from datetime import datetime
from typing import Optional

from src.app.core.constants import OTAStatus, RolloutStrategy
from src.app.schemas.base import BaseSchema, BaseResponse


class OTADeploymentCreate(BaseSchema):
    target_image: str
    previous_image: Optional[str] = None
    strategy: RolloutStrategy = RolloutStrategy.ROLLING
    total_devices: int = 0
    auto_rollback: bool = True
    rollback_threshold_percent: int = 5
    notes: Optional[str] = None


class OTADeploymentUpdate(BaseSchema):
    status: Optional[OTAStatus] = None
    success_count: Optional[int] = None
    failed_count: Optional[int] = None
    notes: Optional[str] = None


class OTADeploymentResponse(BaseResponse):
    target_image: str
    previous_image: Optional[str]
    strategy: str
    status: str
    total_devices: int
    success_count: int
    failed_count: int
    auto_rollback: bool
    rollback_threshold_percent: int
    deployed_by: Optional[uuid.UUID]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    notes: Optional[str]
