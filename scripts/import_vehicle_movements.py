"""Import a daily Summary Report .xlsx into vehicle_movements.

The report has one sheet per vehicle type and one row per movement. Only a time
of day is recorded — the date lives in the filename, and the location is not in
the file at all, so both are supplied here.

Sheet layout (both sheets)::

    A            B                 C
    Hour         <type> in         <type> out
    10:00:10     In
    10:03:03     In
    ...
    10:15:24                       Out
    ...
    13:47:43     In                Out      <- one IN *and* one OUT
    Total        109               94       <- skipped

Usage::

    python scripts/import_vehicle_movements.py "Summary Report _ 25th Aug 2026.xlsx" \\
        --location-name "Open Ground Jagatpur"

    # re-import the same day after a corrected file
    python scripts/import_vehicle_movements.py <file> --location-name <name> --replace

Run with --dry-run first; it reports exactly what would be written and validates
the sheet's own Total row against the rows actually present.
"""

import argparse
import asyncio
import datetime
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import openpyxl
from sqlalchemy import delete, func, select

from src.app.core.constants import MovementDirection, VehicleType
from src.app.db.session import async_session_factory

# Import all models to register them
import src.app.models  # noqa: F401

from src.app.models.camera import Camera
from src.app.models.location import Location
from src.app.models.vehicle_movement import VehicleMovement

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("import_movements")

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

MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)
}


class ImportError_(Exception):
    """Anything that should stop the import with a readable message."""


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def parse_date_from_filename(path: Path) -> datetime.date:
    """Pull the report date out of a name like 'Summary Report _ 25th Aug 2026'.

    Ordinal suffixes are optional and the month may be long or short, so
    '1 January 2026' and '25th Aug 2026' both work.
    """
    name = path.stem
    match = re.search(
        r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?\s+(\d{4})", name
    )
    if not match:
        raise ImportError_(
            f"Could not read a date from the filename {name!r}. "
            f"Expected something like '25th Aug 2026' — pass --date YYYY-MM-DD instead."
        )
    day, month_word, year = match.groups()
    month = MONTHS.get(month_word[:3].lower())
    if not month:
        raise ImportError_(f"Unknown month {month_word!r} in filename {name!r}.")
    try:
        return datetime.date(int(year), month, int(day))
    except ValueError as exc:
        raise ImportError_(f"Invalid date in filename {name!r}: {exc}") from exc


def vehicle_type_for_sheet(sheet_name: str) -> Optional[str]:
    lowered = sheet_name.lower()
    for needle, vtype in SHEET_VEHICLE_TYPES:
        if needle in lowered:
            return vtype
    return None


def _cell_marker(value) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def read_sheet(ws, report_date: datetime.date) -> Tuple[List[Dict], Dict]:
    """Return (movements, report) for one sheet.

    A row may carry an 'In', an 'Out', or BOTH — a row with both means one
    vehicle entered and another left at the same second, and counts as two
    movements. That reading is what makes the computed totals match the
    sheet's own Total row.
    """
    movements: List[Dict] = []
    report = {"rows_read": 0, "blank": 0, "skipped": [], "stated_in": None,
              "stated_out": None}

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

        marks_in = _cell_marker(in_cell) == "in"
        marks_out = _cell_marker(out_cell) == "out"
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


def _as_int(value) -> Optional[int]:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

async def resolve_location(db, location_id: Optional[str], location_name: Optional[str]):
    if location_id:
        loc = (await db.execute(
            select(Location).where(Location.id == uuid.UUID(location_id))
        )).scalars().first()
        if not loc:
            raise ImportError_(f"No location with id {location_id}")
        return loc

    matches = (await db.execute(
        select(Location).where(Location.name.ilike(f"%{location_name}%"))
    )).scalars().all()
    if not matches:
        raise ImportError_(f"No location matching {location_name!r}")
    if len(matches) > 1:
        names = "\n  ".join(f"{m.name}  ({m.id})" for m in matches)
        raise ImportError_(
            f"{location_name!r} matches {len(matches)} locations — "
            f"pass --location-id instead:\n  {names}"
        )
    return matches[0]


async def resolve_camera(db, camera_id: Optional[str], location) -> Optional[uuid.UUID]:
    if not camera_id:
        return None
    cam = (await db.execute(
        select(Camera).where(Camera.id == uuid.UUID(camera_id))
    )).scalars().first()
    if not cam:
        raise ImportError_(f"No camera with id {camera_id}")
    return cam.id


async def existing_count(db, location_id, day_start, day_end, vehicle_types) -> int:
    return (await db.execute(
        select(func.count())
        .select_from(VehicleMovement)
        .where(
            VehicleMovement.location_id == location_id,
            VehicleMovement.recorded_at >= day_start,
            VehicleMovement.recorded_at <= day_end,
            VehicleMovement.vehicle_type.in_(vehicle_types),
        )
    )).scalar_one()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

async def run(args) -> int:
    path = Path(args.xlsx_path).expanduser()
    if not path.exists():
        raise ImportError_(f"File not found: {path}")

    report_date = (
        datetime.date.fromisoformat(args.date)
        if args.date else parse_date_from_filename(path)
    )
    logger.info("Report date: %s (times read as IST)", report_date)

    workbook = openpyxl.load_workbook(path, data_only=True)

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
        raise ImportError_(
            "No usable sheets. Expected names containing 'Two Wheeler' or "
            "'Four Wheeler'."
        )

    # ---- report and validate before touching the database ----
    total_rows = 0
    mismatches = []
    for title, (vtype, movements, report) in per_sheet.items():
        ins = sum(1 for m in movements if m["direction"] == MovementDirection.IN.value)
        outs = len(movements) - ins
        total_rows += len(movements)
        logger.info(
            "Sheet %-14r -> %-12s  IN=%-4d OUT=%-4d  (%d movements from %d rows)",
            title, vtype, ins, outs, len(movements), report["rows_read"],
        )
        for row_no, why in report["skipped"]:
            logger.warning("  row %d skipped — %s", row_no, why)

        # The sheet states its own totals. Disagreement means the file's SUM
        # is stale or rows were added outside it — worth knowing before the
        # numbers reach a dashboard.
        for label, stated, computed in (
            ("IN", report["stated_in"], ins),
            ("OUT", report["stated_out"], outs),
        ):
            if stated is not None and stated != computed:
                mismatches.append((title, label, stated, computed))
                logger.warning(
                    "  Total row says %s=%d but the rows contain %d — "
                    "importing the %d actual rows",
                    label, stated, computed, computed,
                )

    if not total_rows:
        raise ImportError_("Nothing to import — no movement rows found.")

    day_start = datetime.datetime.combine(
        report_date, datetime.time.min, tzinfo=IST
    ).astimezone(datetime.timezone.utc)
    day_end = datetime.datetime.combine(
        report_date, datetime.time.max, tzinfo=IST
    ).astimezone(datetime.timezone.utc)

    async with async_session_factory() as db:
        try:
            location = await resolve_location(db, args.location_id, args.location_name)
            camera_id = await resolve_camera(db, args.camera_id, location)
            logger.info("Location: %s (%s)", location.name, location.id)

            vehicle_types = sorted({v for v, _, _ in per_sheet.values()})
            already = await existing_count(
                db, location.id, day_start, day_end, vehicle_types
            )
            if already and not args.replace:
                raise ImportError_(
                    f"{already} movements already exist for {location.name} on "
                    f"{report_date}. Re-run with --replace to overwrite them, or "
                    f"--date to import a different day."
                )

            if args.dry_run:
                logger.info(
                    "DRY RUN — would %s%d movements",
                    f"delete {already} and insert " if already else "insert ",
                    total_rows,
                )
                return 1 if mismatches else 0

            if already:
                await db.execute(
                    delete(VehicleMovement).where(
                        VehicleMovement.location_id == location.id,
                        VehicleMovement.recorded_at >= day_start,
                        VehicleMovement.recorded_at <= day_end,
                        VehicleMovement.vehicle_type.in_(vehicle_types),
                    )
                )
                logger.info("Replaced: deleted %d existing movements", already)

            for _, (vtype, movements, _) in per_sheet.items():
                db.add_all([
                    VehicleMovement(
                        location_id=location.id,
                        camera_id=camera_id,
                        vehicle_type=vtype,
                        direction=m["direction"],
                        recorded_at=m["recorded_at"],
                    )
                    for m in movements
                ])

            await db.commit()
            logger.info("Imported %d movements for %s on %s",
                        total_rows, location.name, report_date)
            return 1 if mismatches else 0

        except Exception:
            await db.rollback()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a daily Summary Report .xlsx into vehicle_movements.",
    )
    parser.add_argument("xlsx_path", help="Path to the .xlsx file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--location-id", help="Location UUID")
    group.add_argument("--location-name", help="Location name (partial match)")
    parser.add_argument("--camera-id", help="Optional camera UUID for every row")
    parser.add_argument(
        "--date",
        help="YYYY-MM-DD. Defaults to the date read from the filename.",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="Delete this location's movements for that date first. Makes "
             "re-running the same day safe.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would happen without writing anything.",
    )
    args = parser.parse_args()

    try:
        return asyncio.run(run(args))
    except ImportError_ as exc:
        logger.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
