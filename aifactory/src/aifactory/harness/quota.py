"""When an exhausted harness may have quota again, read from its quota message.

A harness that runs out of quota (``failure.QuotaExhausted``) often says when the limit
resets: codex ``try again in 3 days``, Claude ``resets 3pm (Europe/Prague)``. ``retry_at``
turns that into a time; a message without one, or one that does not parse, gives
``now + QUOTA_RECHECK``. The run's quota chain (``run/quota_chain.py``) skips the harness
until then.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

QUOTA_RECHECK = timedelta(hours=1)
"""How long a harness counts as out of quota when its message gives no reset time."""

_IN = re.compile(r"\bin\s+(\d+)\s*(minute|min|hour|hr|day)s?\b", re.IGNORECASE)
_RESETS = re.compile(
    r"\bresets\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)]+)\))?",
    re.IGNORECASE,
)
_UNITS = {"minute": "minutes", "min": "minutes", "hour": "hours", "hr": "hours", "day": "days"}

__all__ = ["QUOTA_RECHECK", "retry_at"]


def _zone(name: str | None, now: datetime) -> tzinfo:
    if name:
        try:
            return ZoneInfo(name.strip())
        except (ZoneInfoNotFoundError, ValueError):
            pass
    local = now.astimezone().tzinfo
    return local if local is not None else UTC


def _resets(match: re.Match[str], now: datetime) -> datetime | None:
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if not meridiem and match.group(2) is None:
        return None  # a bare number is not a time of day
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    if hour > 23 or minute > 59:
        return None
    zone = _zone(match.group(4), now)
    local_now = now.astimezone(zone)
    when = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when <= local_now:
        when += timedelta(days=1)
    return when.astimezone(UTC)


def retry_at(message: str | None, now: datetime | None = None) -> datetime:
    """The time (UTC) the harness of a quota `message` may have quota again; never raises."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    try:
        text = message or ""
        found = _IN.search(text)
        if found is not None:
            amount = int(found.group(1))
            unit = _UNITS[found.group(2).lower()]
            return (current + timedelta(**{unit: amount})).astimezone(UTC)
        reset = _RESETS.search(text)
        if reset is not None:
            when = _resets(reset, current)
            if when is not None:
                return when
    except (ValueError, OverflowError, KeyError):
        pass
    return (current + QUOTA_RECHECK).astimezone(UTC)
