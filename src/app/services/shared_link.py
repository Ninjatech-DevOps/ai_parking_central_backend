import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.app.core.config import settings
from src.app.core.constants import SharedLinkScopeType
from src.app.exceptions.base import BadRequestException, NotFoundException
from src.app.repositories.camera import CameraRepository
from src.app.repositories.device import DeviceRepository
from src.app.repositories.location import LocationRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.repositories.shared_link import SharedLinkRepository


class SharedLinkService:
    def __init__(
        self,
        shared_link_repo: SharedLinkRepository,
        location_repo: LocationRepository,
        device_repo: DeviceRepository,
        camera_repo: CameraRepository,
        slot_repo: ParkingSlotRepository,
    ):
        self.shared_link_repo = shared_link_repo
        self.location_repo = location_repo
        self.device_repo = device_repo
        self.camera_repo = camera_repo
        self.slot_repo = slot_repo

    async def create(self, data: Dict[str, Any], user_id: uuid.UUID) -> Any:
        scope_type = data["scope_type"]

        if scope_type == SharedLinkScopeType.CAMERA:
            if not data.get("camera_ids"):
                raise BadRequestException(detail="camera_ids required for CAMERA scope")
            data["camera_ids"] = json.dumps([str(cid) for cid in data["camera_ids"]])
            data["scope_id"] = None
        elif scope_type == SharedLinkScopeType.LOCATION:
            # Multi-location: location IDs come in camera_ids field
            if data.get("camera_ids"):
                data["camera_ids"] = json.dumps([str(lid) for lid in data["camera_ids"]])
                data["scope_id"] = None
            elif data.get("scope_id"):
                data.pop("camera_ids", None)
            else:
                raise BadRequestException(detail="camera_ids (location_ids) or scope_id required for LOCATION scope")
        else:
            if not data.get("scope_id"):
                raise BadRequestException(detail="scope_id required for non-CAMERA scope")
            data.pop("camera_ids", None)

        if "view_config" in data and data["view_config"] is not None:
            vc = data["view_config"]
            if isinstance(vc, dict):
                data["view_config"] = json.dumps(vc)
            else:
                data["view_config"] = json.dumps(vc.dict() if hasattr(vc, "dict") else vc)

        data["created_by_user_id"] = user_id
        return await self.shared_link_repo.create(data)

    async def get(self, link_id: uuid.UUID) -> Any:
        link = await self.shared_link_repo.get_by_id(link_id)
        if not link:
            raise NotFoundException(detail="Shared link not found")
        return link

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        return await self.shared_link_repo.search(
            skip=skip, limit=limit, search=search, filters=filters
        )

    async def count(
        self,
        search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        return await self.shared_link_repo.count_search(
            search=search, filters=filters
        )

    async def update(self, link_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        link = await self.shared_link_repo.get_by_id(link_id)
        if not link:
            raise NotFoundException(detail="Shared link not found")
        if "view_config" in data and data["view_config"] is not None:
            vc = data["view_config"]
            if isinstance(vc, dict):
                data["view_config"] = json.dumps(vc)
            else:
                data["view_config"] = json.dumps(vc.dict() if hasattr(vc, "dict") else vc)
        return await self.shared_link_repo.update(link_id, data)

    async def delete(self, link_id: uuid.UUID) -> bool:
        link = await self.shared_link_repo.get_by_id(link_id)
        if not link:
            raise NotFoundException(detail="Shared link not found")
        return await self.shared_link_repo.delete(link_id)

    async def validate_public_link(self, token: str, required_page: Optional[str] = None):
        """Validate a public link token and optionally check page access.

        Returns the link object if valid. Raises NotFoundException otherwise.
        """
        link = await self.shared_link_repo.get_by_token(token)
        if not link or not link.is_active:
            raise NotFoundException(detail="Link not found or inactive")

        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            raise NotFoundException(detail="Link has expired")

        if required_page:
            view_config = self._parse_view_config(link)
            pages = view_config.get("pages", []) if view_config else []
            if pages and required_page not in pages:
                raise NotFoundException(detail="Page not available on this link")

        return link

    def _parse_view_config(self, link) -> Optional[Dict]:
        if not link.view_config:
            return None
        try:
            return json.loads(link.view_config)
        except (json.JSONDecodeError, ValueError):
            return None

    async def resolve_public_view(self, token: str) -> Dict[str, Any]:
        link = await self.shared_link_repo.get_by_token(token)
        if not link or not link.is_active:
            raise NotFoundException(detail="Link not found or inactive")

        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            raise NotFoundException(detail="Link has expired")

        await self.shared_link_repo.increment_view_count(link.id)

        location_ids = await self._resolve_location_ids(link)
        camera_filter_ids = self._parse_camera_ids(link)

        locations_data = []
        total_summary = {"total": 0, "available": 0, "occupied": 0, "obstructed": 0}

        for loc_id in location_ids:
            location = await self.location_repo.get_by_id(loc_id)
            if not location:
                continue

            cameras_data, loc_summary = await self._build_location_cameras(
                loc_id, camera_filter_ids
            )
            if not cameras_data:
                continue

            locations_data.append({
                "id": location.id,
                "name": location.name,
                "cameras": cameras_data,
                "summary": loc_summary,
            })

            for key in total_summary:
                total_summary[key] += loc_summary[key]

        return {
            "name": link.name,
            "scope_type": link.scope_type,
            "view_config": self._parse_view_config(link),
            "locations": locations_data,
            "total_summary": total_summary,
        }

    async def _resolve_location_ids(self, link) -> List[uuid.UUID]:
        scope_type = link.scope_type

        if scope_type == SharedLinkScopeType.CAMERA:
            camera_ids = self._parse_camera_ids(link)
            location_ids = set()
            for cam_id in camera_ids:
                camera = await self.camera_repo.get_by_id(cam_id)
                if camera:
                    device = await self.device_repo.get_by_id(camera.device_id)
                    if device:
                        location_ids.add(device.location_id)
            return list(location_ids)

        if scope_type == SharedLinkScopeType.LOCATION:
            # Multi-location: location IDs stored in camera_ids field as JSON
            if link.camera_ids:
                try:
                    ids = json.loads(link.camera_ids)
                    return [uuid.UUID(lid) for lid in ids]
                except (json.JSONDecodeError, ValueError):
                    pass
            # Single location fallback
            if link.scope_id:
                return [link.scope_id]
            return []

        filter_key = {
            SharedLinkScopeType.AREA: "area_id",
            SharedLinkScopeType.VILLAGE: "village_id",
            SharedLinkScopeType.TALUKA: "taluka_id",
            SharedLinkScopeType.CITY: "city_id",
        }.get(scope_type)

        if filter_key:
            locations = await self.location_repo.get_all(
                skip=0, limit=1000,
                filters={filter_key: link.scope_id, "is_active": True}
            )
            return [loc.id for loc in locations]

        return []

    def _parse_camera_ids(self, link) -> Optional[List[uuid.UUID]]:
        if link.scope_type != SharedLinkScopeType.CAMERA or not link.camera_ids:
            return None
        try:
            ids = json.loads(link.camera_ids)
            return [uuid.UUID(cid) for cid in ids]
        except (json.JSONDecodeError, ValueError):
            return None

    async def _build_location_cameras(
        self,
        location_id: uuid.UUID,
        camera_filter_ids: Optional[List[uuid.UUID]],
    ) -> Tuple[List[Dict], Dict]:
        devices = await self.device_repo.get_by_location_id(location_id)
        cameras_data = []
        summary = {"total": 0, "available": 0, "occupied": 0, "obstructed": 0}

        for device in devices:
            cameras = await self.camera_repo.get_by_device_id(device.id)
            for cam in cameras:
                if not cam.is_active:
                    continue
                if camera_filter_ids and cam.id not in camera_filter_ids:
                    continue

                slots = await self.slot_repo.get_by_camera_id(cam.id)
                slot_list = []
                for s in slots:
                    slot_list.append({
                        "id": s.id,
                        "label": s.label,
                        "state": s.state,
                        "slot_type": s.slot_type or "GENERAL",
                        "detected_vehicle_type": s.detected_vehicle_type,
                        "capacity_car": s.capacity_car,
                        "capacity_two_wheeler": s.capacity_two_wheeler,
                        "occupied_car": s.occupied_car,
                        "occupied_two_wheeler": s.occupied_two_wheeler,
                        "polygon_coords": s.polygon_coords,
                        "pos_x1": s.pos_x1,
                        "pos_y1": s.pos_y1,
                        "pos_x2": s.pos_x2,
                        "pos_y2": s.pos_y2,
                    })
                    summary["total"] += 1
                    state = s.state
                    if state == "EMPTY":
                        summary["available"] += 1
                    elif state == "VEHICLE":
                        summary["occupied"] += 1
                    elif state == "OBSTRUCTED":
                        summary["obstructed"] += 1

                scheme = "https" if settings.MINIO_SECURE else "http"
                base_path = f"{scheme}://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/debug/{device.device_id}/{cam.position_label}"
                debug_url = f"{base_path}/latest.jpg"
                clean_url = f"{base_path}/clean.jpg"

                cameras_data.append({
                    "id": cam.id,
                    "device_id": device.id,
                    "position_label": cam.position_label,
                    "status": cam.status,
                    "frame_width": cam.frame_width,
                    "frame_height": cam.frame_height,
                    "debug_frame_url": debug_url,
                    "clean_frame_url": clean_url,
                    "slots": slot_list,
                })

        return cameras_data, summary
