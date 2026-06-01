from __future__ import annotations

from datetime import datetime, timezone

_MIN_HOURS = 18.0
_MAX_HOURS = 30.0


def in_window(end_date: datetime, now: datetime | None = None) -> bool:
    """Return True when 18h ≤ hours-to-resolution ≤ 30h."""
    if now is None:
        now = datetime.now(tz=timezone.utc)
    hours_left = (end_date - now).total_seconds() / 3600
    return _MIN_HOURS <= hours_left <= _MAX_HOURS
