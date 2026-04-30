from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def parse_when(value: Optional[str | datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_utc_naive(value)

    raw = str(value).strip()
    if not raw:
        return None

    rel = re.fullmatch(r"(\d+)\s*([hdw])", raw.lower())
    if rel:
        amount = int(rel.group(1))
        unit = rel.group(2)
        if unit == "h":
            return utcnow_naive() - timedelta(hours=amount)
        if unit == "d":
            return utcnow_naive() - timedelta(days=amount)
        if unit == "w":
            return utcnow_naive() - timedelta(weeks=amount)

    try:
        return to_utc_naive(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def in_window(
    published_at: Optional[datetime],
    since: Optional[datetime],
    until: Optional[datetime],
) -> bool:
    published_at = to_utc_naive(published_at)
    since = to_utc_naive(since)
    until = to_utc_naive(until)
    if published_at is None:
        return True
    if since and published_at < since:
        return False
    if until and published_at > until:
        return False
    return True
