"""Shared Summary Report parsing and storage for vehicle movements.

Used by both the CLI importer (``scripts/import_vehicle_movements.py``) and the
upload endpoint, so the two can never disagree about how a sheet is read.

Expected workbook: one sheet per vehicle type, one row per movement::

    A            B                 C
    Hour         <type> in         <type> out
    10:00:10     In
    10:15:24                       Out
    13:47:43     In                Out      <- one IN *and* one OUT
    Total        109               94       <- skipped, used to validate
"""

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from sqlalchemy import delete, func, select

from src.app.core.constants import MovementDirection, VehicleType
from src.app.models.vehicle_movement import VehicleMovement

logger = logging.getLogger("vehicle_movement_import")

# Times in the report are local wall-clock. Stored in UTC like every other
# timestamp in this database.
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Sheet name -> vehicle type. Matched on a substring of the lowercased name so
# "Four Wheeler", "Four  Wheeler" and "4 Wheeler" all land in the same place.
SHEET_VEHICLE_TYPES: List[Tuple[str, str]] = [
    ("two", VehicleType.TWO_WHEELER.value),
    ("2 wheel", VehicleType.TWO_WHEELER.value),
    ("bike", VehicleType.TWO_WHEELER.value),
    ("four", VehicleType.CAR.value),
    ("4 wheel", VehicleType.CAR.value),
    ("car", VehicleType.CAR.value),
]


class WorkbookError(Exception):
    """The workbook cannot be read as a Summary Report."""


def vehicle_type_for_sheet(sheet_name: str) -> Optional[str]:
    lowered = sheet_name.lower()
    for needle, vtype in SHEET_VEHICLE_TYPES:
        if needle in lowered:
            return vtype
    return None


def _marker(value) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _as_int(value) -> Optional[int]:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def read_sheet(ws, report_date: datetime.date) -> Tuple[List[Dict], Dict]:
    """Return (movements, report) for one sheet.

    A row may carry an 'In', an 'Out', or BOTH — a row with both means one
    vehicle entered and another left at the same second, and counts as two
    movements. That reading is what makes the computed totals match the
    sheet's own Total row.
    """
    movements: List[Dict] = []
    report: Dict[str, Any] = {
        "rows_read": 0, "blank": 0, "skipped": [],
        "stated_in": None, "stated_out": None,
    }

    for row_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        time_cell = row[0] if len(row) > 0 else None
        in_cell = row[1] if len(row) > 1 else None
        out_cell = row[2] if len(row) > 2 else None

        if time_cell is None and in_cell is None and out_cell is None:
            report["blank"] += 1
            continue

        # The trailing 'Total' row carries the sheet's own figures. Keep them
        # for validation rather than importing them.
        if isinstance(time_cell, str) and "total" in time_cell.lower():
            report["stated_in"] = _as_int(in_cell)
            report["stated_out"] = _as_int(out_cell)
            continue

        if isinstance(time_cell, datetime.datetime):
            time_cell = time_cell.time()
        if not isinstance(time_cell, datetime.time):
            report["skipped"].append((row_no, f"not a time: {time_cell!r}"))
            continue

        marks_in = _marker(in_cell) == "in"
        marks_out = _marker(out_cell) == "out"
        if not marks_in and not marks_out:
            report["skipped"].append((row_no, "neither In nor Out"))
            continue

        recorded_at = datetime.datetime.combine(
            report_date, time_cell, tzinfo=IST
        ).astimezone(datetime.timezone.utc)

        if marks_in:
            movements.append({"recorded_at": recorded_at,
                              "direction": MovementDirection.IN.value})
        if marks_out:
            movements.append({"recorded_at": recorded_at,
                              "direction": MovementDirection.OUT.value})
        report["rows_read"] += 1

    return movements, report


def parse_workbook(source, report_date: datetime.date) -> Dict[str, Tuple[str, List[Dict], Dict]]:
    """Parse every recognised sheet. ``source`` is a path or a file-like object."""
    try:
        workbook = openpyxl.load_workbook(source, data_only=True, read_only=False)
    except Exception as exc:
        raise WorkbookError(f"Could not read the file as .xlsx: {exc}") from exc

    per_sheet: Dict[str, Tuple[str, List[Dict], Dict]] = {}
    for worksheet in workbook.worksheets:
        vtype = vehicle_type_for_sheet(worksheet.title)
        if not vtype:
            logger.warning("Sheet %r — no vehicle type in the name, skipped",
                           worksheet.title)
            continue
        movements, report = read_sheet(worksheet, report_date)
        per_sheet[worksheet.title] = (vtype, movements, report)

    if not per_sheet:
        raise WorkbookError(
            "No usable sheets. Expected sheet names containing 'Two Wheeler' "
            "or 'Four Wheeler'."
        )
    return per_sheet


def summarise(per_sheet: Dict[str, Tuple[str, List[Dict], Dict]]) -> Dict[str, Any]:
    """Per-sheet counts plus any disagreement with the sheet's own Total row."""
    sheets = []
    warnings: List[str] = []
    total = 0

    for title, (vtype, movements, report) in per_sheet.items():
        ins = sum(1 for m in movements if m["direction"] == MovementDirection.IN.value)
        outs = len(movements) - ins
        total += len(movements)
        sheets.append({
            "sheet": title, "vehicle_type": vtype,
            "total_in": ins, "total_out": outs,
            "movements": len(movements), "rows_read": report["rows_read"],
        })

        for row_no, why in report["skipped"]:
            warnings.append(f"{title}: row {row_no} skipped — {why}")

        # The sheet states its own totals. Disagreement means the file's SUM is
        # stale or rows were added outside it — worth surfacing before the
        # numbers reach a dashboard.
        for label, stated, computed in (
            ("IN", report["stated_in"], ins),
            ("OUT", report["stated_out"], outs),
        ):
            if stated is not None and stated != computed:
                warnings.append(
                    f"{title}: Total row says {label}={stated} but the rows "
                    f"contain {computed} — importing the {computed} actual rows"
                )

    return {"sheets": sheets, "total_movements": total, "warnings": warnings}


def day_bounds(report_date: datetime.date) -> Tuple[datetime.datetime, datetime.datetime]:
    """The report date as a UTC [start, end] pair, IST days."""
    start = datetime.datetime.combine(report_date, datetime.time.min, tzinfo=IST)
    end = datetime.datetime.combine(report_date, datetime.time.max, tzinfo=IST)
    return start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc)


async def count_existing(db, location_id, report_date, vehicle_types) -> int:
    start, end = day_bounds(report_date)
    return (await db.execute(
        select(func.count()).select_from(VehicleMovement).where(
            VehicleMovement.location_id == location_id,
            VehicleMovement.recorded_at >= start,
            VehicleMovement.recorded_at <= end,
            VehicleMovement.vehicle_type.in_(vehicle_types),
        )
    )).scalar_one()


async def store(
    db,
    location_id,
    report_date: datetime.date,
    per_sheet: Dict[str, Tuple[str, List[Dict], Dict]],
    camera_id=None,
    replace: bool = False,
) -> int:
    """Write the parsed movements. Returns how many existing rows were removed.

    Deletion is scoped to this location, this date and only the vehicle types
    present in the file, so replacing one day can never touch another day or
    another site. Caller commits.
    """
    vehicle_types = sorted({v for v, _, _ in per_sheet.values()})
    removed = 0

    if replace:
        start, end = day_bounds(report_date)
        removed = await count_existing(db, location_id, report_date, vehicle_types)
        if removed:
            await db.execute(
                delete(VehicleMovement).where(
                    VehicleMovement.location_id == location_id,
                    VehicleMovement.recorded_at >= start,
                    VehicleMovement.recorded_at <= end,
                    VehicleMovement.vehicle_type.in_(vehicle_types),
                )
            )

    for _, (vtype, movements, _) in per_sheet.items():
        db.add_all([
            VehicleMovement(
                location_id=location_id,
                camera_id=camera_id,
                vehicle_type=vtype,
                direction=m["direction"],
                recorded_at=m["recorded_at"],
            )
            for m in movements
        ])

    return removed
