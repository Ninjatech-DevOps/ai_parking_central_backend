"""Service: Handle config sync from edge devices (cameras + slots via MQTT)."""

import logging
from typing import Dict, List

from sqlalchemy import delete as sa_delete

from src.app.core.constants import CameraStatus, SlotState
from src.app.models.slot_event import SlotEvent
from src.app.repositories.device import DeviceRepository
from src.app.repositories.camera import CameraRepository
from src.app.repositories.parking_slot import ParkingSlotRepository

logger = logging.getLogger("ai_parking.services.device_sync")


class DeviceSyncService:
    def __init__(
        self,
        device_repo: DeviceRepository,
        camera_repo: CameraRepository,
        slot_repo: ParkingSlotRepository,
    ):
        self.device_repo = device_repo
        self.camera_repo = camera_repo
        self.slot_repo = slot_repo

    async def sync_camera(self, device_id_str: str, action: str, camera_data: Dict) -> None:
        device = await self.device_repo.get_by_device_id(device_id_str)
        if not device:
            logger.warning("Sync camera from unknown device: %s", device_id_str)
            return

        label = camera_data.get("label", "")

        if action == "delete":
            camera = await self.camera_repo.get_by_device_and_label(device.id, label)
            if camera:
                await self.camera_repo.update(camera.id, {"is_active": False})
                logger.info("Camera '%s' deactivated on device %s", label, device_id_str)
            return

        # Create or update
        source = camera_data.get("source")
        camera_type = camera_data.get("camera_type")

        camera = await self.camera_repo.get_by_device_and_label(device.id, label)
        if camera:
            update_data = {"status": CameraStatus.ACTIVE, "is_active": True}
            if source:
                update_data["source"] = source
            if camera_type:
                update_data["camera_type"] = camera_type
            await self.camera_repo.update(camera.id, update_data)
            logger.info("Camera '%s' updated on device %s", label, device_id_str)
        else:
            create_data = {
                "device_id": device.id,
                "position_label": label,
                "status": CameraStatus.ACTIVE,
                "is_active": True,
            }
            if source:
                create_data["source"] = source
            if camera_type:
                create_data["camera_type"] = camera_type
            await self.camera_repo.create(create_data)
            logger.info("Camera '%s' created on device %s", label, device_id_str)

    async def sync_slots(
        self, device_id_str: str, action: str, camera_label: str, slots_data: List[Dict]
    ) -> None:
        device = await self.device_repo.get_by_device_id(device_id_str)
        if not device:
            logger.warning("Sync slots from unknown device: %s", device_id_str)
            return

        if not device.zone_id:
            logger.warning("Device %s has no zone assigned — cannot sync slots", device_id_str)
            return

        camera = await self.camera_repo.get_by_device_and_label(device.id, camera_label)
        if not camera:
            logger.warning(
                "Camera '%s' not found on device %s — sync camera first",
                camera_label, device_id_str,
            )
            return

        # Sync slots: update existing, create new.
        # Only remove slots NOT in the incoming list when action="create" (explicit
        # client-side CRUD). For "upsert" (periodic sync), never delete — central
        # may have slots the client doesn't know about yet.
        created = 0
        updated = 0
        deleted = 0

        incoming_labels = {s["label"] for s in slots_data}

        if action in ("create", "full_sync"):
            # Explicit CRUD from client — safe to reconcile deletions
            existing_slots = await self.slot_repo.get_by_camera_id(camera.id)
            for slot in existing_slots:
                if slot.label not in incoming_labels:
                    await self.slot_repo.soft_delete(slot.id)
                    deleted += 1

        # Create or update incoming slots
        for slot_data in slots_data:
            label = slot_data["label"]
            existing = await self.slot_repo.get_by_camera_and_label(camera.id, label)

            update_data = {
                "polygon_coords": slot_data.get("polygon_coords"),
                "pos_x1": slot_data.get("pos_x1"),
                "pos_y1": slot_data.get("pos_y1"),
                "pos_x2": slot_data.get("pos_x2"),
                "pos_y2": slot_data.get("pos_y2"),
            }

            if existing:
                await self.slot_repo.update(existing.id, update_data)
                updated += 1
            elif action == "create":
                await self.slot_repo.create({
                    "label": label,
                    "zone_id": device.zone_id,
                    "camera_id": camera.id,
                    "state": SlotState.EMPTY,
                    **update_data,
                })
                created += 1

        logger.info(
            "Synced slots for camera '%s' on device %s: %d created, %d updated, %d deleted",
            camera_label, device_id_str, created, updated, deleted,
        )
