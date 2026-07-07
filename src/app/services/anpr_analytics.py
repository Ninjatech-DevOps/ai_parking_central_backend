"""Reusable ANPR session analytics.

Revenue, occupancy-summary and chart builders shared by the authenticated ANPR
Sessions PDF export (``anpr_session`` route) and the public shared-link view
(``public_view`` route), so both render identical cards/charts/revenue from a
single implementation. Extracted (behaviour-preserving) from the anpr_session
route module.
"""
import math
import uuid
from datetime import datetime, timedelta
from typing import Optional, Set

from sqlalchemy import select as sa_select, func

from src.app.models.anpr_session import AnprSession
from src.app.models.location import Location

# IST offset — buckets/labels align to local hours (12am, 1am, ...).
IST = timedelta(hours=5, minutes=30)

REVENUE_PER_HOUR = 15  # Rs per hour, any part of an hour billed as a full hour.


def _ev(v) -> str:
    """Extract .value from enum, or return str as-is."""
    return v.value if hasattr(v, "value") else str(v)


def _naive(dt):
    """Strip tzinfo (values are UTC) so we can do plain arithmetic on them."""
    return dt.replace(tzinfo=None) if (dt is not None and dt.tzinfo is not None) else dt


def session_revenue(entry, exit_) -> int:
    """Revenue for one session: ceil(hours) * rate (min 1 hour).
    Active sessions (no exit) are charged up to now."""
    if entry is None:
        return 0
    end = exit_ or datetime.now(entry.tzinfo)
    secs = (end - entry).total_seconds()
    hours = max(1, math.ceil(secs / 3600)) if secs > 0 else 1
    return hours * REVENUE_PER_HOUR


def compact_duration(text: str) -> str:
    """'3 hr 36 min' -> '3h 36m' so it fits the dense table."""
    return (text or "").replace(" hrs", "h").replace(" hr", "h").replace(" mins", "m").replace(" min", "m")


def build_inout_chart(items, start, end, ist=IST) -> dict:
    """In/Out bars bucketed by ENTRY time, so the bar sums equal the cards:
    in[b] = entries in bucket b; out[b] = of those, how many have exited.
    Bucket size adapts to the window span: <=2h -> 15 min, <=26h -> hourly,
    else daily. Default window (no filter) = today 10 AM -> 6 PM (IST), so the
    Hourly Entry Pattern shows the standard 10 AM ... 6 PM business hours.
    """
    if start is None:
        start = (datetime.utcnow() + ist).replace(hour=10, minute=0, second=0, microsecond=0) - ist
    if end is None:
        end = (datetime.utcnow() + ist).replace(hour=18, minute=0, second=0, microsecond=0) - ist
    # Work in IST so buckets/labels align to local hours (12am, 1am, ...).
    start_ist, end_ist = _naive(start) + ist, _naive(end) + ist
    if end_ist < start_ist:
        end_ist = start_ist

    span_h = (end_ist - start_ist).total_seconds() / 3600
    if span_h <= 2:
        step, gran = timedelta(minutes=15), "15min"
        t = start_ist.replace(minute=(start_ist.minute // 15) * 15, second=0, microsecond=0)
    elif span_h <= 26:
        step, gran = timedelta(hours=1), "hour"
        # Clamp the hourly view to business hours 10 AM - 6 PM (IST): a full-day
        # window still renders the standard 10 AM ... 6 PM pattern, while a
        # narrower intra-day filter (e.g. 1-4 PM) is respected as chosen.
        day = start_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        c_start = max(start_ist, day + timedelta(hours=10))
        c_end = min(end_ist, day + timedelta(hours=18))
        if c_start <= c_end:
            start_ist, end_ist = c_start, c_end
        t = start_ist.replace(minute=0, second=0, microsecond=0)
    else:
        step, gran = timedelta(days=1), "day"
        t = start_ist.replace(hour=0, minute=0, second=0, microsecond=0)

    edges = []
    while t <= end_ist:
        edges.append(t)
        t += step
    if not edges:
        edges = [start_ist]
    n = len(edges)
    step_s = step.total_seconds()

    labels = []
    for el in edges:
        if gran == "15min":
            labels.append(el.strftime("%-I:%M"))
        elif gran == "hour":
            labels.append(el.strftime("%-I%p").lower())   # "10am"
        else:
            labels.append(el.strftime("%-d %b"))          # "1 Jul"

    # Bucket by ENTRY time, only within the window -> bar sums == the cards.
    in_vals, out_vals = [0] * n, [0] * n
    for s in items:
        et = _naive(s.entry_time) + ist
        if et < start_ist or et > end_ist:
            continue
        i = min(max(int((et - edges[0]).total_seconds() // step_s), 0), n - 1)
        in_vals[i] += 1
        if s.exit_time:
            out_vals[i] += 1
    return {"labels": labels, "in": in_vals, "out": out_vals, "granularity": gran}


def duration_breakdown(items, start, end, ist=IST) -> list:
    """Count completed sessions (with an out time) by stay duration bucket.
    Only entries within the window, so the counts tie to the Out card."""
    if start is None:
        start = (datetime.utcnow() + ist).replace(hour=0, minute=0, second=0, microsecond=0) - ist
    if end is None:
        end = datetime.utcnow()
    start_ist, end_ist = _naive(start) + ist, _naive(end) + ist
    buckets = [0, 0, 0, 0, 0]   # <30m, 30-60m, 1-2h, 2-8h, >8h
    for s in items:
        if not s.exit_time:
            continue
        et = _naive(s.entry_time) + ist
        if et < start_ist or et > end_ist:
            continue
        m = (_naive(s.exit_time) - _naive(s.entry_time)).total_seconds() / 60
        if m < 30:
            buckets[0] += 1
        elif m < 60:
            buckets[1] += 1
        elif m < 120:
            buckets[2] += 1
        elif m < 480:
            buckets[3] += 1
        else:
            buckets[4] += 1
    labels = ["< 30 min", "30m - 1h", "1 - 2 hrs", "2 - 8 hrs", "> 8 hrs"]
    return [{"label": labels[i], "count": buckets[i]} for i in range(5)]


async def anpr_occupancy_summary(
    db,
    location_ids: Optional[Set[uuid.UUID]] = None,
    start=None,
    end=None,
) -> dict:
    """Occupancy cards for the ANPR report (Total / In / Out / Available):
      Total     = configured location slots (locations.total_*_slots)
      In        = entries in the window (all IN reads for that time)
      Out       = of those entries, how many have exited (has an out time)
      Available = max(0, Total - (In - Out))   (Total minus still-parked)
    ``location_ids`` scopes the query (None = all in-scope). Default window
    (no range chosen) = today 00:00 -> now (IST).
    """
    ist = IST
    if start is None:
        start = (datetime.utcnow() + ist).replace(hour=0, minute=0, second=0, microsecond=0) - ist
    if end is None:
        end = datetime.utcnow()

    def _scope(q, col):
        if location_ids is not None:
            return q.where(col.in_(location_ids))
        return q

    async def _counts(q):
        car = bike = 0
        for vtype, count in (await db.execute(q)).all():
            if _ev(vtype) == "CAR":
                car = count
            elif _ev(vtype) == "TWO_WHEELER":
                bike = count
        return car, bike

    # Total — configured capacity per vehicle type.
    loc_q = _scope(sa_select(
        func.coalesce(func.sum(Location.total_car_slots), 0),
        func.coalesce(func.sum(Location.total_two_wheeler_slots), 0),
    ).where(Location.is_active.is_(True)), Location.id)
    car_total, bike_total = (await db.execute(loc_q)).one()

    # In = all entries in the window; Out = of those, how many have exited.
    car_in, bike_in = await _counts(_scope(
        sa_select(AnprSession.vehicle_type, func.count())
        .where(AnprSession.entry_time >= start, AnprSession.entry_time <= end)
        .group_by(AnprSession.vehicle_type), AnprSession.location_id))
    car_out, bike_out = await _counts(_scope(
        sa_select(AnprSession.vehicle_type, func.count())
        .where(AnprSession.entry_time >= start, AnprSession.entry_time <= end,
               AnprSession.exit_time.is_not(None))
        .group_by(AnprSession.vehicle_type), AnprSession.location_id))

    # Overall occupancy % = still-parked (In - Out) vehicles / total capacity.
    occupied = max(0, car_in - car_out) + max(0, bike_in - bike_out)
    total_cap = car_total + bike_total
    occupancy_pct = round(occupied / total_cap * 100) if total_cap else 0

    return {
        "car": {"total": car_total, "in": car_in, "out": car_out,
                "available": max(0, car_total - (car_in - car_out))},
        "bike": {"total": bike_total, "in": bike_in, "out": bike_out,
                 "available": max(0, bike_total - (bike_in - bike_out))},
        "occupancy_pct": occupancy_pct,
    }


async def build_anpr_report(db, location_ids, items, start=None, end=None) -> dict:
    """Assemble the ANPR report payload shared by the PDF and the shared link:
    summary cards (Total/In/Out/Available + Occupancy %, Revenue Rs, Accuracy %)
    and analytics (In/Out chart + Duration breakdown)."""
    summary = await anpr_occupancy_summary(db, location_ids, start, end)
    total_revenue = sum(
        session_revenue(s.entry_time, s.exit_time) for s in items if s.exit_time
    )
    summary["revenue"] = f"{total_revenue:,}"
    summary["accuracy_pct"] = 100  # ANPR plate-recognition accuracy
    analytics = {
        "chart": build_inout_chart(items, start, end),
        "duration": duration_breakdown(items, start, end),
    }
    return {"summary": summary, "analytics": analytics}
