#!/usr/bin/env python3
"""
Seed sample ANPR data directly into the database.

Inserts:
1. Updates an existing location with total_car_slots / total_two_wheeler_slots
2. Updates an existing camera with module_type = ANPR
3. Creates an AnprCameraConfig for that camera
4. Creates sample AnprRecords + AnprSessions (50 records, ~25 sessions)

Usage:
    # Run from project root with DB accessible
    python scripts/seed_anpr_data.py

    # Or specify DB URL
    DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db python scripts/seed_anpr_data.py
"""

import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.models.anpr_camera_config import AnprCameraConfig
from src.app.models.anpr_record import AnprRecord
from src.app.models.anpr_session import AnprSession
from src.app.models.camera import Camera
from src.app.models.device import Device
from src.app.models.location import Location

# ─── Sample plates ────────────────────────────────────────────────────────────
PLATES = [
    "GJ01AB1234", "GJ01CD5678", "GJ01EF9012", "GJ01GH3456",
    "GJ05JK7890", "GJ05LM2345", "GJ05NP6789", "GJ05QR0123",
    "GJ27ST4567", "GJ27UV8901", "MH01AA1111", "MH04CC3333",
    "DL01GG7777", "KA01II9999", "RJ14EE5555",
]


async def seed(db_url: str):
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # 1. Find first location + device + camera
        loc_result = await db.execute(select(Location).where(Location.is_active == True).limit(1))
        location = loc_result.scalars().first()
        if not location:
            print("ERROR: No locations found. Create a location first.")
            return

        dev_result = await db.execute(
            select(Device).where(Device.location_id == location.id, Device.is_active == True).limit(1)
        )
        device = dev_result.scalars().first()
        if not device:
            print(f"ERROR: No devices found at location '{location.name}'. Create a device first.")
            return

        cam_result = await db.execute(
            select(Camera).where(Camera.device_id == device.id, Camera.is_active == True).limit(1)
        )
        camera = cam_result.scalars().first()
        if not camera:
            print(f"ERROR: No cameras found on device '{device.device_id}'. Create a camera first.")
            return

        print(f"Using: Location='{location.name}', Device='{device.device_id}', Camera='{camera.position_label}'")

        # 2. Update location with slot totals
        location.total_car_slots = 50
        location.total_two_wheeler_slots = 20
        print(f"  Set location slot totals: 50 car, 20 two-wheeler")

        # 3. Update camera module_type to ANPR
        camera.module_type = "ANPR"
        print(f"  Set camera module_type = ANPR")

        # 4. Create ANPR camera config (upsert)
        existing = await db.execute(
            select(AnprCameraConfig).where(AnprCameraConfig.camera_id == camera.id)
        )
        if not existing.scalars().first():
            config = AnprCameraConfig(
                camera_id=camera.id,
                roi_coords='[[100,100],[500,100],[500,400],[100,400]]',
                trigger_line='[[100,250],[500,250]]',
                direction="IN",
                is_active=True,
            )
            db.add(config)
            print(f"  Created ANPR camera config")
        else:
            print(f"  ANPR camera config already exists")

        # 5. Generate sample ANPR records + sessions
        now = datetime.now(timezone.utc)
        records_created = 0
        sessions_created = 0
        active_sessions: dict[str, AnprSession] = {}

        for i in range(50):
            plate = random.choice(PLATES)
            vehicle_type = random.choice(["CAR", "CAR", "CAR", "TWO_WHEELER"])
            recorded_at = now - timedelta(hours=random.uniform(0, 48))

            # Decide direction
            if plate in active_sessions and random.random() < 0.7:
                direction = "OUT"
            else:
                direction = "IN"

            gemini_conf = round(random.uniform(0.85, 0.99), 2)
            paddle_conf = round(random.uniform(0.80, 0.97), 2)

            record = AnprRecord(
                device_id=device.id,
                camera_id=camera.id,
                location_id=location.id,
                city_id=location.city_id,
                number_plate=plate,
                vehicle_type=vehicle_type,
                direction=direction,
                image_url=f"https://api-minio.projectanddemoserver.com/ai-parking/anpr/seed_{plate}_{i}.jpg",
                gemini_result=plate,
                paddle_result=plate,
                confidence_gemini=gemini_conf,
                confidence_paddle=paddle_conf,
                recorded_at=recorded_at,
            )
            db.add(record)
            await db.flush()
            records_created += 1

            if direction == "IN":
                session = AnprSession(
                    location_id=location.id,
                    city_id=location.city_id,
                    number_plate=plate,
                    vehicle_type=vehicle_type,
                    entry_record_id=record.id,
                    entry_time=recorded_at,
                    entry_image_url=record.image_url,
                    is_active=True,
                )
                db.add(session)
                await db.flush()
                active_sessions[plate] = session
                sessions_created += 1
            elif direction == "OUT" and plate in active_sessions:
                session = active_sessions.pop(plate)
                session.exit_record_id = record.id
                session.exit_time = recorded_at + timedelta(minutes=random.uniform(15, 480))
                session.exit_image_url = record.image_url
                session.is_active = False

        await db.commit()
        print(f"\nSeeded: {records_created} ANPR records, {sessions_created} sessions")
        print(f"Active sessions (still parked): {len(active_sessions)}")
        print("Done!")


if __name__ == "__main__":
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://ai_parking:ai_parking_pass@localhost:5480/ai_parking_central"
    )
    print(f"Connecting to: {db_url}")
    asyncio.run(seed(db_url))
