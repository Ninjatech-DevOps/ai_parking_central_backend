"""Reusable AI-Parking occupancy analytics.

Hourly-occupancy and summary-stat builders shared by the AI Parking Occupancy
PDF export (``parking_history`` route) and the public shared-link view
(``public_view`` route), so both render identical charts/stats.
"""
from datetime import timedelta

from src.app.utils.timewindow import OP_END_HOUR, OP_START_HOUR

IST = timedelta(hours=5, minutes=30)


def _fmt_hour_label(h: int) -> str:
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def _peak_hour_display(hourly: dict) -> tuple:
    if not hourly:
        return "-", 0
    peak_val = max(hourly.values())
    if peak_val == 0:
        return "-", 0
    peak_h = min(h for h, v in hourly.items() if v == peak_val)
    return _fmt_hour_label(peak_h), peak_val


def build_hourly_occupancy(items) -> list:
    """Hourly occupancy across the operating window, summed across every camera.

    For each hour we pick each CAMERA's busiest scan in that hour, then sum
    those picks across cameras. Picking a single scan per hour across all
    cameras (the old behaviour) reported one camera's numbers as the whole
    site, so the chart contradicted the summary tiles on multi-camera
    locations.

    ``items`` are ParkingScan ORM rows.
    """
    hourly = []
    # Buckets are keyed by their START hour, so the range stops one short of
    # OP_END_HOUR: with 10..19 that is hours 10-18, covering 10:00-18:59.
    # Driven by the shared constants so the window is changed in one place.
    for h in range(OP_START_HOUR, OP_END_HOUR):
        # camera_id -> that camera's busiest scan within this hour
        best_by_cam: dict = {}
        for s in items:
            if not s.recorded_at:
                continue
            t = s.recorded_at + IST
            if t.hour != h:
                continue
            occ = (s.car_occupied or 0) + (s.two_wheeler_occupied or 0)
            cur = best_by_cam.get(s.camera_id)
            if cur is None or occ > (cur.car_occupied or 0) + (cur.two_wheeler_occupied or 0):
                best_by_cam[s.camera_id] = s

        picks = best_by_cam.values()
        hourly.append({
            "hour": h,
            "occ_car": sum(s.car_occupied or 0 for s in picks),
            "tot_car": sum(s.car_total or 0 for s in picks),
            "occ_bike": sum(s.two_wheeler_occupied or 0 for s in picks),
            "tot_bike": sum(s.two_wheeler_total or 0 for s in picks),
        })
    return hourly


def build_occupancy_stats(rows: list, hourly: list) -> dict:
    hourly_occ = {d.get("hour", 0): d.get("occ_car", 0) + d.get("occ_bike", 0) for d in hourly}
    peak_label, peak_count = _peak_hour_display(hourly_occ)
    peak_h = max(hourly_occ, key=hourly_occ.get) if hourly_occ else -1
    peak_h_data = next((d for d in hourly if d.get("hour") == peak_h), None)
    peak_car = peak_h_data.get("occ_car", 0) if peak_h_data else 0
    peak_2w = peak_h_data.get("occ_bike", 0) if peak_h_data else 0

    all_car_pcts = []
    all_bike_pcts = []
    max_cars = 0
    max_bikes = 0
    peak_occ_pct = 0
    for r in hourly:
        car_occ = r.get("occ_car", 0)
        car_cap = r.get("tot_car", 0)
        bike_occ = r.get("occ_bike", 0)
        bike_cap = r.get("tot_bike", 0)
        car_pct = round(car_occ / car_cap * 100) if car_cap > 0 else 0
        bike_pct = round(bike_occ / bike_cap * 100) if bike_cap > 0 else 0
        peak_occ_pct = max(peak_occ_pct, car_pct, bike_pct)
        max_cars = max(max_cars, car_occ)
        max_bikes = max(max_bikes, bike_occ)
        if car_cap > 0:
            all_car_pcts.append(car_pct)
        if bike_cap > 0:
            all_bike_pcts.append(bike_pct)
    avg_car_occ = round(sum(all_car_pcts) / len(all_car_pcts)) if all_car_pcts else 0
    avg_bike_occ = round(sum(all_bike_pcts) / len(all_bike_pcts)) if all_bike_pcts else 0

    return {
        "peak_hour_label": peak_label,
        "peak_hour_count": peak_count,
        "peak_hour_car": peak_car,
        "peak_hour_2w": peak_2w,
        "peak_occupancy_pct": peak_occ_pct,
        "avg_car_occ": avg_car_occ,
        "avg_2w_occ": avg_bike_occ,
        "max_cars": max_cars,
        "max_2w": max_bikes,
    }


def build_parking_report(items) -> dict:
    hourly = build_hourly_occupancy(items)
    return {"hourly": hourly, "stats": build_occupancy_stats([], hourly)}
