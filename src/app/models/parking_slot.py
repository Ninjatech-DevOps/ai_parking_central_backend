from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import SlotState, SlotType
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class ParkingSlot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "parking_slots"

    label: Mapped[str] = mapped_column(String(20), nullable=False)
    zone_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True
    )
    camera_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(
        SAEnum(SlotState, name="slot_state_enum"),
        nullable=False,
        default=SlotState.EMPTY,
    )
    slot_type: Mapped[str] = mapped_column(String(20), nullable=False, default=SlotType.GENERAL.value)
    detected_vehicle_type: Mapped[str] = mapped_column(String(20), nullable=True)
    # Per-type capacity (max vehicles this slot can hold)
    capacity_car: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capacity_two_wheeler: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Per-type occupied count (currently detected vehicles)
    occupied_car: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occupied_two_wheeler: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_obstruction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Polygon coordinates from client ROI (JSON: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]])
    polygon_coords: Mapped[str] = mapped_column(Text, nullable=True)
    # Bounding box (auto-calculated from polygon for canvas)
    pos_x1: Mapped[int] = mapped_column(Integer, nullable=True)
    pos_y1: Mapped[int] = mapped_column(Integer, nullable=True)
    pos_x2: Mapped[int] = mapped_column(Integer, nullable=True)
    pos_y2: Mapped[int] = mapped_column(Integer, nullable=True)

    zone = relationship("Zone", back_populates="parking_slots", lazy="selectin")
    camera = relationship("Camera", back_populates="slots", lazy="selectin")
    slot_events = relationship("SlotEvent", back_populates="parking_slot", lazy="noload")
