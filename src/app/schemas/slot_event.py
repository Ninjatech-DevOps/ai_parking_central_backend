import uuid
from datetime import datetime
from typing import Dict, List, Optional

from src.app.core.constants import SlotState
from src.app.schemas.base import BaseSchema


class SlotEventCreate(BaseSchema):
    parking_slot_id: uuid.UUID
    previous_state: Optional[SlotState] = None
    new_state: SlotState
    device_id: Optional[uuid.UUID] = None


class SlotEventResponse(BaseSchema):
    id: uuid.UUID
    parking_slot_id: uuid.UUID
    previous_state: Optional[str]
    new_state: str
    device_id: Optional[uuid.UUID]
    detected_vehicle_type: Optional[str] = None
    is_mismatched: bool = False
    image_url: Optional[str] = None
    recorded_at: datetime


class ParkingSessionResponse(BaseSchema):
    entry_event_id: str
    slot_id: str
    slot_label: str
    camera_label: Optional[str]
    location_name: Optional[str]
    location_id: Optional[str]
    area_name: Optional[str]
    city_name: Optional[str]
    camera_id: Optional[str]
    event_type: str
    detected_vehicle_type: Optional[str] = None
    image_url: Optional[str] = None
    entry_time: str
    exit_time: Optional[str]
    duration_minutes: Optional[float]
    is_active: bool


# --- Occupancy Analysis ---

class HourlyOccupancy(BaseSchema):
    hour: int
    occupancy_pct: float
    occupied_slots: int
    total_slots: int
    mismatch_pct: float


class PeakPeriod(BaseSchema):
    start_hour: int
    end_hour: int
    avg_occupancy_pct: float
    avg_mismatch_pct: float
    label: str


class ZoneOccupancyAnalysis(BaseSchema):
    zone_id: str
    zone_name: str
    floor_label: str
    location_name: str
    area_name: Optional[str]
    total_slots: int
    slots_by_type: Dict[str, int]
    avg_occupancy_pct: float
    avg_mismatch_pct: float
    hourly_breakdown: List[HourlyOccupancy]
    peak_periods: List[PeakPeriod]
    insight: str


class OccupancyAnalysisResponse(BaseSchema):
    threshold: int
    slot_type_filter: Optional[str]
    start_date: str
    end_date: str
    zones: List[ZoneOccupancyAnalysis]
    global_peak_hour: Optional[int]
    global_avg_occupancy_pct: float
    global_avg_mismatch_pct: float
    hotspot_zones: List[str]
