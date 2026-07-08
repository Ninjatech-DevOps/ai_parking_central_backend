"""Reusable AI-Parking occupancy analytics.

Hourly-occupancy and summary-stat builders shared by the AI Parking Occupancy
PDF export (``parking_history`` route) and the public shared-link view
(``public_view`` route), so both render identical charts/stats.
"""
from datetime import timedelta

# IST offset — hourly buckets/labels align to local hours (10 AM ... 6 PM).
IST = timedelta(hours=5, minutes=30)


def _fmt_hour_label(h: int) -> str:
    """10 -> '10 AM', 13 -> '1 PM', etc."""
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def _peak_hour_display(hourly: dict) -> tuple:
    """Return (peak_hour_label, occupied_count) for the busiest hour.
    Always returns the single first hour with the highest count.
    Returns ("-", 0) if no data."""
    if not hourly:
        return "-", 0
    peak_val = max(hourly.values())
    if peak_val == 0:
        return "-", 0
    peak_h = min(h for h, v in hourly.items() if v == peak_val)
    return _fmt_hour_label(peak_h), peak_val


def build_hourly_occupancy(items) -> list:
    """Hourly occupancy (10 AM - 6 PM): for each hour pick the single scan
    with the highest total occupancy. Uses UTC minute % 5 == 0 filter, and
    IST hour for bucketing. ``items`` are ParkingScan ORM rows."""
    valid = [s for s in items if s.recorded_at and s.recorded_at.minute % 5 == 0]
    hourly = []
    for h in range(10, 19):
        best = None
        best_occ = -1
        for s in valid:
            t = s.recorded_at + IST
            if t.hour == h:
                occ = s.car_occupied + s.two_wheeler_occupied
                if occ > best_occ:
                    best_occ = occ
                    best = s
        hourly.append({
            "hour": h,
            "occ_car": best.car_occupied if best else 0,
            "tot_car": best.car_total if best else 0,
            "occ_bike": best.two_wheeler_occupied if best else 0,
            "tot_bike": best.two_wheeler_total if best else 0,
        })
    return hourly


def build_occupancy_stats(rows: list, hourly: list) -> dict:
    """Summary stat tiles derived from ``hourly`` (same data the chart shows)."""
    hourly_occ = {d.get("hour", 0): d.get("occ_car", 0) + d.get("occ_bike", 0) for d in hourly}
    peak_label, peak_count = _peak_hour_display(hourly_occ)
    peak_h_data = next((d for d in hourly if d.get("hour") == (max(hourly_occ, key=hourly_occ.get) if hourly_occ else -1)), None)
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
    """Assemble the AI-Parking report: hourly occupancy (10 AM-6 PM) + summary
    stats. Only scans at exact 5-minute marks (UTC) are used."""
    hourly = build_hourly_occupancy(items)
    return {"hourly": hourly, "stats": build_occupancy_stats([], hourly)}
