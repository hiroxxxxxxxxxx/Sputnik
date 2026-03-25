"""NY カレンダー・日次 as_of 解決のテスト。"""
from __future__ import annotations

from datetime import date, datetime, timezone

from avionics.calendar import NY_TZ, as_of_for_daily_signal_persist


def test_as_of_daily_after_ny_close_weekday() -> None:
    """月曜 NY 17:00（RTH 外・クローズ後）→ 当日。"""
    dt = datetime(2025, 3, 10, 17, 0, 0, tzinfo=NY_TZ)
    assert as_of_for_daily_signal_persist(dt.astimezone(timezone.utc)) == date(2025, 3, 10)


def test_as_of_daily_pre_market_weekday() -> None:
    """月曜 NY 08:00 → 前営業日（金）。"""
    dt = datetime(2025, 3, 10, 8, 0, 0, tzinfo=NY_TZ)
    assert as_of_for_daily_signal_persist(dt.astimezone(timezone.utc)) == date(2025, 3, 7)


def test_as_of_daily_weekend() -> None:
    """日曜 NY 正午 → 金曜。"""
    dt = datetime(2025, 3, 9, 12, 0, 0, tzinfo=NY_TZ)
    assert as_of_for_daily_signal_persist(dt.astimezone(timezone.utc)) == date(2025, 3, 7)


def test_as_of_daily_tuesday_early_morning() -> None:
    """火曜 NY 03:00 → 月曜（直前に完了したセッション）。"""
    dt = datetime(2025, 3, 11, 3, 0, 0, tzinfo=NY_TZ)
    assert as_of_for_daily_signal_persist(dt.astimezone(timezone.utc)) == date(2025, 3, 10)


def test_as_of_daily_rth_uses_previous_business_day() -> None:
    """RTH 場中は前営業日。"""
    dt = datetime(2025, 3, 10, 12, 0, 0, tzinfo=NY_TZ)
    assert as_of_for_daily_signal_persist(dt.astimezone(timezone.utc)) == date(2025, 3, 7)
