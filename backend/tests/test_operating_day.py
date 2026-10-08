from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import operating_day
from app.operating_day import operating_day_bounds_utc

UTC = timezone.utc


def test_bounds_for_a_regular_instant():
    # 10:00 en Bogota (UTC-5) del 7 de octubre de 2026.
    now = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)

    assert operating_day_bounds_utc(now) == (
        datetime(2026, 10, 7, 5, 0),
        datetime(2026, 10, 8, 5, 0),
    )


def test_start_of_the_day_is_inclusive_in_bogota_time():
    # 23:59:59.999999 del 6 en Bogota: todavia es el dia operativo del 6.
    just_before = datetime(2026, 10, 7, 4, 59, 59, 999999, tzinfo=UTC)
    # 00:00:00 del 7 en Bogota: ya es el dia operativo del 7.
    at_start = datetime(2026, 10, 7, 5, 0, tzinfo=UTC)

    assert operating_day_bounds_utc(just_before) == (
        datetime(2026, 10, 6, 5, 0),
        datetime(2026, 10, 7, 5, 0),
    )
    assert operating_day_bounds_utc(at_start) == (
        datetime(2026, 10, 7, 5, 0),
        datetime(2026, 10, 8, 5, 0),
    )


def test_day_lasts_exactly_24_hours():
    for day in (date(2026, 1, 1), date(2026, 3, 8), date(2026, 10, 7), date(2026, 12, 31)):
        now = datetime(day.year, day.month, day.day, 18, 30, tzinfo=UTC)
        start, end = operating_day_bounds_utc(now)
        assert end - start == timedelta(hours=24)


def test_bounds_are_naive_utc():
    start, end = operating_day_bounds_utc(datetime(2026, 10, 7, 15, 0, tzinfo=UTC))

    assert start.tzinfo is None
    assert end.tzinfo is None


def test_bogota_date_rules_when_it_differs_from_the_utc_date():
    # 22:00 del 7 en Bogota = 03:00Z del 8: la fecha UTC ya cambio, el dia operativo no.
    evening = datetime(2026, 10, 8, 3, 0, tzinfo=UTC)
    # 22:00 del 6 en Bogota = 03:00Z del 7.
    other_evening = datetime(2026, 10, 7, 3, 0, tzinfo=UTC)

    assert operating_day_bounds_utc(evening) == (
        datetime(2026, 10, 7, 5, 0),
        datetime(2026, 10, 8, 5, 0),
    )
    assert operating_day_bounds_utc(other_evening) == (
        datetime(2026, 10, 6, 5, 0),
        datetime(2026, 10, 7, 5, 0),
    )


def test_bounds_do_not_depend_on_the_timezone_of_the_input():
    now_utc = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
    now_bogota = now_utc.astimezone(ZoneInfo("America/Bogota"))

    assert operating_day_bounds_utc(now_bogota) == operating_day_bounds_utc(now_utc)


def test_naive_input_is_rejected():
    with pytest.raises(ValueError):
        operating_day_bounds_utc(datetime(2026, 10, 7, 15, 0))


def test_default_instant_comes_from_utc_now(monkeypatch):
    monkeypatch.setattr(
        operating_day, "utc_now", lambda: datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
    )

    assert operating_day_bounds_utc() == (
        datetime(2026, 10, 7, 5, 0),
        datetime(2026, 10, 8, 5, 0),
    )
