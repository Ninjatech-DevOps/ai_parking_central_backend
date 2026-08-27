"""Copy a live shared link's data into the local database for testing.

The public shared-link endpoints need no credentials, so a link token is enough
to pull a real location's history down to a dev machine -- no live DB access, no
VPN, nothing to request from ops.

    python -m scripts.import_live_shared_link \
        --url https://ai-parking-central-frontend.projectanddemoserver.com/view/<TOKEN>

What lands locally:

    states / cities        synthetic parents, only because locations.city_id and
                           cities.state_id are NOT NULL. Names are placeholders.
    locations              real id and name. Slot totals are reconstructed as the
                           max car_total / two_wheeler_total seen across scans --
                           the link's own pages do not expose the configured
                           figures, and this matches them in practice.
    devices / cameras      real ids, from the canvas payload and the scan rows.
    parking_slots          real ids, positions and polygons, when the link
                           exposes the canvas.
    parking_scans          the history rows -- the point of the exercise.
    shared_links           a local link reusing the SAME token, so the identical
                           URL works against localhost.

Everything is keyed by the live UUIDs and written with ON CONFLICT DO NOTHING,
so re-running is safe and repeated imports converge rather than duplicate.

The fetch step caches every page under --cache, so a re-import costs nothing.
Use --import-only to rebuild from that cache without touching the network.

NOT a migration or a backup tool: it reconstructs just enough of the hierarchy to
make one link's pages render locally. Do not point it at a production database.
"""

import argparse
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from sqlalchemy import text

from src.app.db.session import async_session_factory

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("import_live")

DEFAULT_API = "https://ai-parking-central-backend.projectanddemoserver.com/api/v1"

# Deterministic ids for the synthetic parents, so re-running never makes a second
# set and two different links imported into the same DB share them.
SYNTH_STATE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
SYNTH_CITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")

PAGE_SIZE = 100  # the endpoint's hard cap


# ─────────────────────────────────────────────────────────────
# Fetch
# ─────────────────────────────────────────────────────────────
def extract_token(url_or_token: str) -> str:
    """Accept a bare token or any URL that ends in one."""
    if "/" not in url_or_token:
        return url_or_token.strip()
    path = urlparse(url_or_token).path.rstrip("/")
    token = path.rsplit("/", 1)[-1]
    if not token:
        raise SystemExit(f"Could not find a token in: {url_or_token}")
    return token


def _get(api: str, token: str, path: str, **params) -> Optional[dict]:
    url = f"{api}/public/view/{token}{path}"
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code == 404:
        # The link's view_config.pages decides which pages exist; a 404 here
        # means this link simply does not expose that one.
        logger.info("  %s -> 404 (not enabled on this link)", path or "/")
        return None
    resp.raise_for_status()
    return resp.json()


def fetch(api: str, token: str, cache: Path, start: Optional[str], end: Optional[str]) -> Dict[str, Any]:
    cache.mkdir(parents=True, exist_ok=True)
    window = {}
    if start:
        window["start_date"] = start
    if end:
        window["end_date"] = end

    logger.info("Fetching from %s", api)
    canvas = _get(api, token, "")
    if canvas is None:
        raise SystemExit("The base view returned 404 -- is the token correct and the link active?")
    logger.info("  link: %s (%d location(s))", canvas.get("name"), len(canvas.get("locations", [])))

    scans: List[dict] = []
    page = 1
    while True:
        data = _get(api, token, "/parking-history", page=page, page_size=PAGE_SIZE, **window)
        if data is None:
            break
        items = data.get("items", [])
        scans.extend(items)
        total = data.get("total", 0)
        logger.info("  parking-history page %d/%s -- %d rows (%d total)",
                    page, data.get("total_pages", "?"), len(items), total)
        if not items or len(scans) >= total:
            break
        page += 1

    payload = {"token": token, "api": api, "canvas": canvas, "scans": scans}
    out = cache / f"{token}.json"
    out.write_text(json.dumps(payload, indent=1))
    logger.info("Cached %d scan row(s) -> %s", len(scans), out)
    return payload


# ─────────────────────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────────────────────
def _u(value) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _dt(value) -> Optional[datetime]:
    """Parse an API timestamp into an aware datetime.

    asyncpg binds timestamptz strictly -- a str raises rather than being coerced,
    so the ISO text the API returns has to be parsed before it reaches the driver.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _device_code(scan: dict, device_id: uuid.UUID) -> str:
    """devices.device_id is the human code (e.g. 'RPI-102'), not the PK."""
    return scan.get("device_name") or f"IMPORTED-{str(device_id)[:8]}"


async def load(payload: Dict[str, Any]) -> None:
    canvas = payload["canvas"]
    scans = payload["scans"]
    token = payload["token"]

    locations = canvas.get("locations", [])
    if not locations:
        raise SystemExit("The link exposes no locations -- nothing to import.")

    # ── derive the hierarchy ────────────────────────────────
    city_id = next((_u(s.get("city_id")) for s in scans if s.get("city_id")), None) or SYNTH_CITY_ID

    devices: Dict[uuid.UUID, str] = {}
    cameras: Dict[uuid.UUID, dict] = {}
    for s in scans:
        did, cid = _u(s.get("device_id")), _u(s.get("camera_id"))
        if did and did not in devices:
            devices[did] = _device_code(s, did)
        if cid and cid not in cameras:
            cameras[cid] = {"device_id": did, "label": s.get("camera_label") or "Cam"}

    # The canvas carries frame dimensions and the real position_label; prefer it.
    for loc in locations:
        for cam in loc.get("cameras", []):
            cid, did = _u(cam.get("id")), _u(cam.get("device_id"))
            entry = cameras.setdefault(cid, {"device_id": did, "label": "Cam"})
            entry["device_id"] = entry.get("device_id") or did
            entry["label"] = cam.get("position_label") or entry["label"]
            entry["frame_width"] = cam.get("frame_width")
            entry["frame_height"] = cam.get("frame_height")
            entry["slots"] = cam.get("slots", [])
            if did and did not in devices:
                devices[did] = f"IMPORTED-{str(did)[:8]}"

    primary_location = _u(locations[0]["id"])
    # Every device must hang off a location; scans only name one location per row,
    # so attribute them all to the link's first location.
    loc_for_device = {d: primary_location for d in devices}

    async with async_session_factory() as db:
        # ── synthetic parents (NOT NULL FKs) ────────────────
        await db.execute(text("""
            INSERT INTO states (id, name, code, country)
            VALUES (:id, 'Imported', 'IMP', 'India') ON CONFLICT (id) DO NOTHING
        """), {"id": SYNTH_STATE_ID})
        await db.execute(text("""
            INSERT INTO cities (id, name, state_id)
            VALUES (:id, 'Imported City', :state) ON CONFLICT (id) DO NOTHING
        """), {"id": city_id, "state": SYNTH_STATE_ID})

        # ── locations ───────────────────────────────────────
        for loc in locations:
            lid = _u(loc["id"])
            rows = [s for s in scans if _u(s.get("location_id")) == lid] or scans
            car_total = max((s.get("car_total") or 0 for s in rows), default=0)
            tw_total = max((s.get("two_wheeler_total") or 0 for s in rows), default=0)
            await db.execute(text("""
                INSERT INTO locations (id, name, city_id, location_type, total_capacity,
                                       total_car_slots, total_two_wheeler_slots, is_active)
                VALUES (:id, :name, :city, 'OPEN', :cap, :car, :tw, true)
                ON CONFLICT (id) DO UPDATE
                   SET total_car_slots = EXCLUDED.total_car_slots,
                       total_two_wheeler_slots = EXCLUDED.total_two_wheeler_slots
            """), {"id": lid, "name": loc.get("name") or "Imported Location",
                   "city": city_id, "cap": car_total + tw_total,
                   "car": car_total, "tw": tw_total})
            logger.info("location %s (%s) car=%d 2w=%d", loc.get("name"), lid, car_total, tw_total)

        # ── devices ─────────────────────────────────────────
        for did, code in devices.items():
            await db.execute(text("""
                INSERT INTO devices (id, device_id, location_id, status, is_active)
                VALUES (:id, :code, :loc, 'ONLINE', true) ON CONFLICT (id) DO NOTHING
            """), {"id": did, "code": code, "loc": loc_for_device[did]})
        logger.info("devices: %d", len(devices))

        # ── cameras ─────────────────────────────────────────
        made = 0
        for cid, cam in cameras.items():
            if not cid or not cam.get("device_id"):
                continue
            await db.execute(text("""
                INSERT INTO cameras (id, device_id, position_label, status, is_active,
                                     module_type, frame_width, frame_height)
                VALUES (:id, :dev, :label, 'ACTIVE', true, 'AI_PARKING', :fw, :fh)
                ON CONFLICT (id) DO UPDATE
                   SET frame_width = COALESCE(EXCLUDED.frame_width, cameras.frame_width),
                       frame_height = COALESCE(EXCLUDED.frame_height, cameras.frame_height)
            """), {"id": cid, "dev": cam["device_id"], "label": cam["label"],
                   "fw": cam.get("frame_width"), "fh": cam.get("frame_height")})
            made += 1
        logger.info("cameras: %d", made)

        # ── slots (only present when the canvas is exposed) ──
        slots = 0
        for cid, cam in cameras.items():
            for s in cam.get("slots") or []:
                sid = _u(s.get("id"))
                if not sid:
                    continue
                await db.execute(text("""
                    INSERT INTO parking_slots (id, label, camera_id, state, slot_type,
                        pos_x1, pos_y1, pos_x2, pos_y2, polygon_coords,
                        capacity_car, capacity_two_wheeler, occupied_car, occupied_two_wheeler,
                        detected_vehicle_type, is_active)
                    VALUES (:id, :label, :cam, :state, :stype, :x1, :y1, :x2, :y2, :poly,
                            :cc, :ct, :oc, :ot, :dvt, true)
                    ON CONFLICT (id) DO NOTHING
                """), {"id": sid, "label": s.get("label") or "S", "cam": cid,
                       "state": s.get("state") or "EMPTY", "stype": s.get("slot_type") or "GENERAL",
                       "x1": s.get("pos_x1"), "y1": s.get("pos_y1"),
                       "x2": s.get("pos_x2"), "y2": s.get("pos_y2"),
                       "poly": s.get("polygon_coords"),
                       "cc": s.get("capacity_car") or 0, "ct": s.get("capacity_two_wheeler") or 0,
                       "oc": s.get("occupied_car") or 0, "ot": s.get("occupied_two_wheeler") or 0,
                       "dvt": s.get("detected_vehicle_type")})
                slots += 1
        logger.info("slots: %d", slots)

        # ── scans ───────────────────────────────────────────
        known_cams = set(cameras)
        inserted = skipped = 0
        for s in scans:
            sid, did, cid, lid = (_u(s.get("id")), _u(s.get("device_id")),
                                  _u(s.get("camera_id")), _u(s.get("location_id")))
            rec = _dt(s.get("recorded_at"))
            # recorded_at is NOT NULL and the camera FK must resolve, so a row
            # missing either is dropped rather than failing the whole import.
            if not (sid and did and cid and lid and rec) or cid not in known_cams:
                skipped += 1
                continue
            await db.execute(text("""
                INSERT INTO parking_scans (id, device_id, camera_id, location_id, city_id,
                    image_url, car_occupied, car_available, car_total,
                    two_wheeler_occupied, two_wheeler_available, two_wheeler_total,
                    has_obstruction, recorded_at)
                VALUES (:id, :dev, :cam, :loc, :city, :img, :co, :ca, :ct, :to_, :ta, :tt,
                        :obs, :rec)
                ON CONFLICT (id) DO NOTHING
            """), {"id": sid, "dev": did, "cam": cid, "loc": lid,
                   "city": _u(s.get("city_id")) or city_id, "img": s.get("image_url"),
                   "co": s.get("car_occupied") or 0, "ca": s.get("car_available") or 0,
                   "ct": s.get("car_total") or 0,
                   "to_": s.get("two_wheeler_occupied") or 0,
                   "ta": s.get("two_wheeler_available") or 0,
                   "tt": s.get("two_wheeler_total") or 0,
                   "obs": bool(s.get("has_obstruction")), "rec": rec})
            inserted += 1
        logger.info("scans: %d queued, %d skipped (unresolved parents)", inserted, skipped)

        # ── a local link on the SAME token ──────────────────
        admin = (await db.execute(text("SELECT id FROM users ORDER BY created_at LIMIT 1"))).scalar()
        if admin:
            await db.execute(text("""
                INSERT INTO shared_links (id, token, name, scope_type, camera_ids,
                                          created_by_user_id, is_active, view_count, view_config)
                VALUES (:id, :token, :name, 'LOCATION', :cams, :user, true, 0, :vc)
                ON CONFLICT (token) DO UPDATE
                   SET camera_ids = EXCLUDED.camera_ids,
                       view_config = EXCLUDED.view_config,
                       is_active = true
            """), {"id": uuid.uuid4(), "token": token,
                   "name": (canvas.get("name") or "Imported") + " (local)",
                   "cams": json.dumps([str(_u(l["id"])) for l in locations]),
                   "user": admin,
                   "vc": json.dumps(canvas.get("view_config") or {"pages": ["parking_history"]})})
            logger.info("shared link ready on the same token: %s", token)
        else:
            logger.warning("No users in the local DB -- skipped creating the shared link.")

        await db.commit()


# ─────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="Public view URL or bare token")
    ap.add_argument("--api", default=DEFAULT_API, help=f"Live API base (default: {DEFAULT_API})")
    ap.add_argument("--cache", default="data/live_import", help="Where fetched JSON is kept")
    ap.add_argument("--start-date", help="YYYY-MM-DD, narrows what is pulled")
    ap.add_argument("--end-date", help="YYYY-MM-DD")
    ap.add_argument("--fetch-only", action="store_true", help="Download and cache, do not import")
    ap.add_argument("--import-only", action="store_true", help="Import from cache, no network")
    args = ap.parse_args()

    token = extract_token(args.url)
    cache = Path(args.cache)

    if args.import_only:
        f = cache / f"{token}.json"
        if not f.exists():
            raise SystemExit(f"No cached payload at {f} -- run without --import-only first.")
        payload = json.loads(f.read_text())
        logger.info("Loaded %d cached scan row(s) from %s", len(payload["scans"]), f)
    else:
        payload = fetch(args.api, token, cache, args.start_date, args.end_date)

    if args.fetch_only:
        logger.info("Fetch complete (--fetch-only); nothing written to the database.")
        return

    asyncio.run(load(payload))
    logger.info("Done. Open: http://localhost:5173/view/%s", token)


if __name__ == "__main__":
    main()
