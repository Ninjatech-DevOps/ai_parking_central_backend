import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.models.slot_event import SlotEvent
from src.app.models.parking_slot import ParkingSlot
from src.app.models.location import Location

import csv
import io

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/slot-events")
async def export_slot_events(
    location_id: uuid.UUID = Query(None),
    start_date: Optional[str] = Query(None, description="ISO format: 2026-05-01T00:00:00"),
    end_date: Optional[str] = Query(None, description="ISO format: 2026-05-10T23:59:59"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
):
    """Export slot events as CSV for a location and date range."""
    query = (
        select(
            SlotEvent.recorded_at,
            ParkingSlot.label,
            SlotEvent.previous_state,
            SlotEvent.new_state,
            Location.name,
        )
        .join(ParkingSlot, ParkingSlot.id == SlotEvent.parking_slot_id)
        .join(Location, Location.id == ParkingSlot.zone_id, isouter=True)
        .order_by(SlotEvent.recorded_at.desc())
        .limit(10000)
    )

    if location_id:
        # Get all slot IDs for this location
        from src.app.models.zone import Zone
        from src.app.models.floor import Floor
        query = (
            select(
                SlotEvent.recorded_at,
                ParkingSlot.label,
                SlotEvent.previous_state,
                SlotEvent.new_state,
            )
            .join(ParkingSlot, ParkingSlot.id == SlotEvent.parking_slot_id)
            .join(Zone, Zone.id == ParkingSlot.zone_id)
            .join(Floor, Floor.id == Zone.floor_id)
            .where(Floor.location_id == location_id)
            .order_by(SlotEvent.recorded_at.desc())
            .limit(10000)
        )

    if start_date:
        query = query.where(SlotEvent.recorded_at >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.where(SlotEvent.recorded_at <= datetime.fromisoformat(end_date))

    result = await db.execute(query)
    rows = result.all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Slot", "Previous State", "New State"])
    for row in rows:
        writer.writerow([
            row[0].isoformat() if row[0] else "",
            row[1] or "",
            row[2] or "",
            row[3] or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=slot_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"},
    )
