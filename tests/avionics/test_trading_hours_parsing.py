"""tradingHours/liquidHours のパース正規化テスト（IB形式差異の吸収）。"""

from __future__ import annotations

from datetime import date

from avionics.ib.trading_hours import core_session_from_hours_raw, core_start_from_hours_raw, parse_trading_hours


def test_parse_trading_hours_normalizes_end_date_prefix() -> None:
    raw = "20260325:0830-20260325:1600;20260326:0830-20260326:1600"
    out = parse_trading_hours(raw)
    assert out
    assert out[0].date_str == "20260325"
    assert out[0].sessions == ["0830-1600"]
    assert out[0].close_time == "1600"


def test_core_start_from_hours_raw() -> None:
    raw = "20260325:0830-20260325:1600"
    picked = core_start_from_hours_raw(raw, ny_date=date(2026, 3, 25))
    assert picked == (date(2026, 3, 25), __import__("datetime").time(8, 30))


def test_core_session_from_hours_raw_returns_end() -> None:
    raw = "20260325:0830-20260325:1600"
    picked = core_session_from_hours_raw(raw, ny_date=date(2026, 3, 25))
    assert picked is not None
    d, start, end = picked
    assert d == date(2026, 3, 25)
    assert start.hour == 8 and start.minute == 30
    assert end.hour == 16 and end.minute == 0

