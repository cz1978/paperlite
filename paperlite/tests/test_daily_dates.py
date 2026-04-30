from datetime import date

from paperlite import daily_dates
from paperlite.timeparse import in_window, parse_when



def test_daily_window_uses_selected_date():
    day, since, until = daily_dates.daily_window("2024-01-02")

    assert day == "2024-01-02"
    assert since.isoformat() == "2024-01-01T16:00:00"
    assert until.isoformat() == "2024-01-02T15:59:59.999999"


def test_daily_window_includes_shanghai_day_across_utc_boundary():
    _day, since, until = daily_dates.daily_window("2026-04-29")

    assert in_window(parse_when("2026-04-28T16:30:00Z"), since, until) is True
    assert in_window(parse_when("2026-04-29T15:59:59Z"), since, until) is True
    assert in_window(parse_when("2026-04-29T16:00:00Z"), since, until) is False


def test_parse_daily_date_accepts_date_objects():
    assert daily_dates.parse_daily_date(date(2024, 1, 2)) == date(2024, 1, 2)


def test_parse_daily_date_falls_back_to_local_today(monkeypatch):
    monkeypatch.setattr(daily_dates, "today_local", lambda: date(2026, 4, 29))

    assert daily_dates.parse_daily_date("not-a-date") == date(2026, 4, 29)
