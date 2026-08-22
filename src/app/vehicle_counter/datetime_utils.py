"""IST date handling shared by the vehicle counter's own routes and the
central-system report endpoint.

Timestamps are stored as naive UTC. Operators think in IST, so every date the
browser sends is interpreted as IST and every date rendered back to a human is
converted to IST. Keeping both directions here means there is exactly one
conversion path -- a second copy alongside the first would be free to drift.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.app.exceptions.base import BadRequestException

IST = timezone(timedelta(hours=5, minutes=30))


def to_ist(value: Optional[datetime]) -> Optional[datetime]:
    """Render a stored timestamp in IST for display."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)


def parse_bound(value: Optional[str], end_of_day: bool) -> Optional[datetime]:
    """Parse a date or datetime the browser sent, interpreted as IST.

    Accepts 'YYYY-MM-DD' and 'YYYY-MM-DDTHH:MM[:SS]'. A bare date used as the
    upper bound covers the whole day.
    """
    if not value:
        return None
    text = value.strip().replace("Z", "")
    try:
        if len(text) == 10:  # date only
            parsed = datetime.strptime(text, "%Y-%m-%d")
            if end_of_day:
                parsed = parsed.replace(hour=23, minute=59, second=59)
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError:
        raise BadRequestException(detail=f"Invalid date value: {value}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    # Stored timestamps are naive UTC, so compare against naive UTC.
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def today_bounds() -> tuple[datetime, datetime]:
    """Naive-UTC bounds covering the current IST day.

    Derived through ``parse_bound`` rather than by constructing the datetimes
    directly, so the default range and an explicitly supplied one go through
    exactly the same conversion.
    """
    today = datetime.now(IST).date().isoformat()
    return parse_bound(today, end_of_day=False), parse_bound(today, end_of_day=True)
