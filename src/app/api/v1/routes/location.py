import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.location import LocationRepository
from src.app.repositories.device import DeviceRepository
from src.app.repositories.camera import CameraRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.repositories.area import AreaRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.location import LocationCreate, LocationResponse, LocationUpdate
from src.app.schemas.camera import CanvasResponse, CanvasCamera, CanvasSlot
from src.app.services.location import LocationService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/locations", tags=["Locations"])


def get_location_service(db: AsyncSession = Depends(get_db)) -> LocationService:
    return LocationService(
        location_repo=LocationRepository(db),
        area_repo=AreaRepository(db),
    )


@router.post("", response_model=LocationResponse, status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_MANAGE))])
async def create_location(
    body: LocationCreate, service: LocationService = Depends(get_location_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[LocationResponse])
async def list_locations(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    area_id: uuid.UUID = Query(None),
    city_id: uuid.UUID = Query(None),
    taluka_id: uuid.UUID = Query(None),
    village_id: uuid.UUID = Query(None),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
    location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if area_id: filters["area_id"] = area_id
    if city_id: filters["city_id"] = city_id
    if taluka_id: filters["taluka_id"] = taluka_id
    if village_id: filters["village_id"] = village_id
    repo = LocationRepository(db)
    items = await repo.get_scoped(location_ids, skip=skip, limit=limit, filters=filters or None)
    total = await repo.count_scoped(location_ids, filters=filters or None)
    return build_paginated_response(items, total, page, limit)


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: uuid.UUID,
    service: LocationService = Depends(get_location_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(location_id)


@router.patch("/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: uuid.UUID,
    body: LocationUpdate,
    service: LocationService = Depends(get_location_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    return await service.update(location_id, body.model_dump(exclude_unset=True))


@router.delete("/{location_id}", response_model=MessageResponse)
async def delete_location(
    location_id: uuid.UUID,
    service: LocationService = Depends(get_location_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    await service.delete(location_id)
    return MessageResponse(message="Location deleted successfully")


@router.get("/{location_id}/canvas", response_model=CanvasResponse)
async def get_canvas_data(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
):
    """Get all camera canvas data for a location — slot positions + states."""
    loc_repo = LocationRepository(db)
    location = await loc_repo.get_by_id(location_id)
    if not location:
        from src.app.exceptions.base import NotFoundException
        raise NotFoundException(detail="Location not found")

    dev_repo = DeviceRepository(db)
    cam_repo = CameraRepository(db)
    slot_repo = ParkingSlotRepository(db)

    devices = await dev_repo.get_by_location_id(location_id)
    cameras_data = []

    for device in devices:
        cameras = await cam_repo.get_by_device_id(device.id)
        for cam in cameras:
            if not cam.is_active:
                continue
            slots = await slot_repo.get_all(filters={"camera_id": cam.id})
            cameras_data.append(CanvasCamera(
                id=cam.id,
                device_id=device.id,
                position_label=cam.position_label,
                status=cam.status,
                frame_width=cam.frame_width,
                frame_height=cam.frame_height,
                slots=[
                    CanvasSlot(
                        id=s.id, label=s.label, state=s.state, polygon_coords=s.polygon_coords,
                        pos_x1=s.pos_x1, pos_y1=s.pos_y1,
                        pos_x2=s.pos_x2, pos_y2=s.pos_y2,
                    ) for s in slots
                ],
            ))

    return CanvasResponse(
        location_id=location.id,
        location_name=location.name,
        cameras=cameras_data,
    )
