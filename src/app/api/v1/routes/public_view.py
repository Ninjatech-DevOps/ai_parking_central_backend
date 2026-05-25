from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.session import get_db
from src.app.repositories.camera import CameraRepository
from src.app.repositories.device import DeviceRepository
from src.app.repositories.location import LocationRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.repositories.shared_link import SharedLinkRepository
from src.app.schemas.shared_link import PublicViewResponse
from src.app.services.shared_link import SharedLinkService

router = APIRouter(prefix="/public", tags=["Public View"])


def get_shared_link_service(db: AsyncSession = Depends(get_db)) -> SharedLinkService:
    return SharedLinkService(
        shared_link_repo=SharedLinkRepository(db),
        location_repo=LocationRepository(db),
        device_repo=DeviceRepository(db),
        camera_repo=CameraRepository(db),
        slot_repo=ParkingSlotRepository(db),
    )


@router.get("/view/{token}", response_model=PublicViewResponse)
async def get_public_view(
    token: str,
    service: SharedLinkService = Depends(get_shared_link_service),
):
    return await service.resolve_public_view(token)
