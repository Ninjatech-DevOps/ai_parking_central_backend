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
from typing import Optional

from sqlalchemy import select

from src.app.db.session import async_session_factory
from src.app.services import vehicle_movement_import as importer

# Import all models to register them
import src.app.models  # noqa: F401

from src.app.models.camera import Camera
from src.app.models.location import Location

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("import_movements")

# Parsing lives in the shared service so the CLI and the upload endpoint can
# never disagree about how a sheet is read.
IST = importer.IST

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

    try:
        per_sheet = importer.parse_workbook(path, report_date)
    except importer.WorkbookError as exc:
        raise ImportError_(str(exc)) from exc

    result = importer.summarise(per_sheet)
    for sheet in result["sheets"]:
        logger.info(
            "Sheet %-14r -> %-12s  IN=%-4d OUT=%-4d  (%d movements from %d rows)",
            sheet["sheet"], sheet["vehicle_type"], sheet["total_in"],
            sheet["total_out"], sheet["movements"], sheet["rows_read"],
        )
    for warning in result["warnings"]:
        logger.warning("  %s", warning)

    total_rows = result["total_movements"]
    if not total_rows:
        raise ImportError_("Nothing to import — no movement rows found.")

    async with async_session_factory() as db:
        try:
            location = await resolve_location(db, args.location_id, args.location_name)
            camera_id = await resolve_camera(db, args.camera_id, location)
            logger.info("Location: %s (%s)", location.name, location.id)

            vehicle_types = sorted({v for v, _, _ in per_sheet.values()})
            already = await importer.count_existing(
                db, location.id, report_date, vehicle_types
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
                return 1 if result["warnings"] else 0

            removed = await importer.store(
                db, location.id, report_date, per_sheet,
                camera_id=camera_id, replace=args.replace,
            )
            if removed:
                logger.info("Replaced: deleted %d existing movements", removed)

            await db.commit()
            logger.info("Imported %d movements for %s on %s",
                        total_rows, location.name, report_date)
            return 1 if result["warnings"] else 0

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
