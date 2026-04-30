from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DAILY_TIMEZONE = "Asia/Shanghai"


def today_local() -> date:
    return datetime.now(ZoneInfo(DAILY_TIMEZONE)).date()


def parse_daily_date(value: str | date | None = None) -> date:
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            pass
    return today_local()


def daily_window(value: str | date | None = None) -> tuple[str, datetime, datetime]:
    day = parse_daily_date(value)
    local_zone = ZoneInfo(DAILY_TIMEZONE)
    local_start = datetime.combine(day, time.min, tzinfo=local_zone)
    local_end = local_start + timedelta(days=1) - timedelta(microseconds=1)
    start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    return day.isoformat(), start, end
