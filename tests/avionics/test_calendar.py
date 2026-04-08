"""NY カレンダー基本関数のテスト。"""
from __future__ import annotations

from datetime import date, datetime, timezone

from avionics.calendar import (
    NY_TZ,
    latest_closed_ny_session_date,
    ny_date_now,
    previous_ny_business_day,
)


def test_ny_date_now_after_ny_close_weekday() -> None:
    """月曜 NY 17:00（RTH 外・クローズ後）→ 当日。"""
    dt = datetime(2025, 3, 10, 17, 0, 0, tzinfo=NY_TZ)
    assert ny_date_now(dt.astimezone(timezone.utc)) == date(2025, 3, 10)


def test_ny_date_now_pre_market_weekday() -> None:
    """月曜 NY 08:00 → 当日の日付。"""
    dt = datetime(2025, 3, 10, 8, 0, 0, tzinfo=NY_TZ)
    assert ny_date_now(dt.astimezone(timezone.utc)) == date(2025, 3, 10)


def test_ny_date_now_weekend() -> None:
    """日曜 NY 正午 → 日曜（日付変換のみ）。"""
    dt = datetime(2025, 3, 9, 12, 0, 0, tzinfo=NY_TZ)
    assert ny_date_now(dt.astimezone(timezone.utc)) == date(2025, 3, 9)


def test_ny_date_now_tuesday_early_morning() -> None:
    """火曜 NY 03:00 → 火曜（日付変換のみ）。"""
    dt = datetime(2025, 3, 11, 3, 0, 0, tzinfo=NY_TZ)
    assert ny_date_now(dt.astimezone(timezone.utc)) == date(2025, 3, 11)


def test_previous_ny_business_day_weekend_skip() -> None:
    """月曜の前営業日は金曜。"""
    assert previous_ny_business_day(date(2025, 3, 10)) == date(2025, 3, 7)


def test_latest_closed_ny_session_date_after_close() -> None:
    """平日 17:00 ET は当日を返す。"""
    dt = datetime(2025, 3, 10, 17, 0, 0, tzinfo=NY_TZ)
    assert latest_closed_ny_session_date(dt.astimezone(timezone.utc)) == date(2025, 3, 10)


def test_latest_closed_ny_session_date_in_rth() -> None:
    """平日 RTH 場中は前営業日を返す。"""
    dt = datetime(2025, 3, 10, 12, 0, 0, tzinfo=NY_TZ)
    assert latest_closed_ny_session_date(dt.astimezone(timezone.utc)) == date(2025, 3, 7)


def test_latest_closed_ny_session_date_pre_market() -> None:
    """平日 08:00 ET は前営業日を返す。"""
    dt = datetime(2025, 3, 10, 8, 0, 0, tzinfo=NY_TZ)
    assert latest_closed_ny_session_date(dt.astimezone(timezone.utc)) == date(2025, 3, 7)


def test_latest_closed_ny_session_date_weekend() -> None:
    """週末は前営業日を返す。"""
    dt = datetime(2025, 3, 9, 12, 0, 0, tzinfo=NY_TZ)
    assert latest_closed_ny_session_date(dt.astimezone(timezone.utc)) == date(2025, 3, 7)
