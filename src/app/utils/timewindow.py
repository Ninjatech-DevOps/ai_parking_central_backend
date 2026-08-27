"""Operating-window helpers for the public shared-link page.

That page reports a parking operating day -- 10:00 to 19:00 IST -- rather than
whatever happens to be in the table. Two separate pieces are needed for that:

``operating_window``
    Resolves the request's date parameters into absolute UTC bounds, defaulting
    to today. Index-backed, so it is what actually narrows the scan.

``ist_hours_between``
    A SQL predicate restricting rows to those hours on EVERY day the bounds
    span.

The bounds alone cannot express the window: ``recorded_at BETWEEN <1 Aug 10:00>
AND <3 Aug 19:00>`` runs straight through 2 Aug at 3 AM. The bounds narrow, the
predicate is what makes the window per-day.

Deliberately kept out of ``services/anpr_analytics`` and
``services/parking_analytics``: those builders are shared with the authenticated
PDF exports, and their existing defaults must not move.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import func

from src.app.exceptions.base import BadRequestException

# Fixed offset, matching the convention used across the analytics builders and
# the report routes. IST has no DST, so this never drifts.
IST = timezone(timedelta(hours=5, minutes=30))

# ─────────────────────────────────────────────────────────────
# THE OPERATING DAY -- change the window here and nowhere else.
#
# OP_END_HOUR is EXCLUSIVE: 10..19 means 10:00:00 through 18:59:59, i.e.
# "10 AM to 7 PM". For a 9 AM - 8 PM day, set 9 and 20.
#
# These two numbers drive everything: the absolute bounds (operating_window),
# the per-day SQL predicate (ist_hours_between), the AI-Parking hour buckets
# (parking_analytics.build_hourly_occupancy) and the ANPR chart clamp
# (anpr_analytics.build_inout_chart). The frontend needs no edit -- its axis is
# derived from whichever buckets the API returns.
# ─────────────────────────────────────────────────────────────
OP_START_HOUR = 10
OP_END_HOUR = 19

# Convenience for callers that just want the standard window.
OP_HOURS: Tuple[int, int] = (OP_START_HOUR, OP_END_HOUR)


def _ist_date(value: str, field: str) -> date:
    """Parse a caller-supplied date as an IST calendar date.

    Accepts 'YYYY-MM-DD' and full ISO datetimes. Only the date survives -- the
    hours come from the operating window, and per-day clipping is enforced by
    ``ist_hours_between``, so any time-of-day in the input is not meaningful.
    """
    text = (value or "").strip().replace("Z", "")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise BadRequestException(
            detail=f"Invalid {field}: {value!r}. Expected YYYY-MM-DD."
        )
    # An offset-aware input names an instant, not a date -- read it in IST so
    # '2026-08-01T23:00+00:00' resolves to 2 Aug locally rather than 1 Aug.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(IST)
    return parsed.date()


def operating_window(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[datetime, datetime]:
    """Resolve date parameters to absolute UTC bounds for the operating window.

    Both ends default to today (IST). Returns timezone-AWARE UTC datetimes:
    every timestamp column these bounds are compared against is
    ``DateTime(timezone=True)``, and passing naive values would leave the
    comparison at the driver's mercy.

    The upper bound lands on 19:00 exactly. A row at 19:00:00.000 would pass it,
    but ``ist_hours_between`` excludes hour 19, so the window stays half-open in
    practice.
    """
    today = datetime.now(IST).date()
    first = _ist_date(start_date, "start_date") if start_date else today
    last = _ist_date(end_date, "end_date") if end_date else today

    if last < first:
        raise BadRequestException(detail="end_date must not be before start_date")

    start = datetime.combine(first, time(OP_START_HOUR), tzinfo=IST)
    end = datetime.combine(last, time(OP_END_HOUR), tzinfo=IST)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def ist_hours_between(
    column,
    start_hour: int = OP_START_HOUR,
    end_hour: int = OP_END_HOUR,
):
    """SQL predicate: the column's IST wall-clock hour is in [start_hour, end_hour).

    ``AT TIME ZONE 'Asia/Kolkata'`` rather than the fixed offset used elsewhere:
    identical result, but it reads as the intent and leaves the arithmetic to
    Postgres.

    Not sargable, so callers must keep ANDing it with the absolute bounds from
    ``operating_window`` -- those hit the ``recorded_at`` / ``entry_time``
    indexes and reduce the set this then filters.
    """
    local = func.timezone("Asia/Kolkata", column)
    return func.extract("hour", local).between(start_hour, end_hour - 1)
