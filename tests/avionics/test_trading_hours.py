"""
取引時間パース・スケジュール通知のテスト。
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from avionics.ib.trading_hours import (
    DaySchedule,
    check_upcoming_schedule,
    parse_trading_hours,
)


def test_parse_trading_hours_empty() -> None:
    """空文字・空白のときは []。"""
    assert parse_trading_hours("") == []
    assert parse_trading_hours("   ") == []


def test_parse_trading_hours_single_day() -> None:
    """1日分の形式をパースする。"""
    raw = "20250310:0930-1600"
    out = parse_trading_hours(raw)
    assert len(out) == 1
    assert out[0].date_str == "20250310"
    assert out[0].sessions == ["0930-1600"]
    assert out[0].close_time == "1600"


def test_parse_trading_hours_multiple_days() -> None:
    """セミコロン区切りで複数日。"""
    raw = "20250310:0930-1600;20250311:0930-1300"
    out = parse_trading_hours(raw)
    assert len(out) == 2
    assert out[0].date_str == "20250310"
    assert out[0].close_time == "1600"
    assert out[1].date_str == "20250311"
    assert out[1].close_time == "1300"


def test_parse_trading_hours_multiple_sessions_per_day() -> None:
    """1日複数セッション（カンマ区切り）は最後の終了時刻。"""
    raw = "20250310:0930-1600,1600-1700"
    out = parse_trading_hours(raw)
    assert len(out) == 1
    assert out[0].close_time == "1700"


def test_check_upcoming_schedule_no_changes() -> None:
    """明日・明後日が通常営業ならメッセージなし。"""
    today = date.today()
    schedule_list = [
        DaySchedule(today.strftime("%Y%m%d"), ["0930-1600"], "1600"),
        DaySchedule((today + timedelta(days=1)).strftime("%Y%m%d"), ["0930-1600"], "1600"),
    ]
    msgs = check_upcoming_schedule(schedule_list, days=2)
    assert msgs == []


def test_check_upcoming_schedule_shortened_tomorrow() -> None:
    """明日が短縮営業なら通知が出る。"""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    schedule_list = [
        DaySchedule(today.strftime("%Y%m%d"), ["0930-1600"], "1600"),
        DaySchedule(tomorrow.strftime("%Y%m%d"), ["0930-1300"], "1300"),
    ]
    msgs = check_upcoming_schedule(schedule_list, days=3)
    assert any("短縮営業" in m for m in msgs)
    assert any("1300" in m or "13:00" in m for m in msgs)


def test_check_upcoming_schedule_holiday_tomorrow() -> None:
    """明日がスケジュールに無い（休場）なら通知。"""
    today = date.today()
    schedule_list = [
        DaySchedule(today.strftime("%Y%m%d"), ["0930-1600"], "1600"),
    ]
    msgs = check_upcoming_schedule(schedule_list, days=3)
    assert any("休場" in m or "スキップ" in m for m in msgs)


def test_check_upcoming_schedule_dst_shift() -> None:
    """今日と明日の終了が1時間ズレていれば DST 通知。"""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    schedule_list = [
        DaySchedule(today.strftime("%Y%m%d"), ["0930-1600"], "1600"),
        DaySchedule(tomorrow.strftime("%Y%m%d"), ["0930-1700"], "1700"),
    ]
    msgs = check_upcoming_schedule(schedule_list, days=3)
    assert any("夏" in m or "冬" in m or "切り替わ" in m for m in msgs)


@pytest.mark.asyncio
async def test_fetch_trading_hours_async_no_connection_returns_empty() -> None:
    """接続失敗時は [] を返す（例外は握りつぶす）。"""
    from avionics.ib.schedule_scan import _contract_for_symbol, fetch_trading_hours_async

    ib = MagicMock()
    ib.reqContractDetailsAsync = AsyncMock(side_effect=ConnectionError())
    contract = _contract_for_symbol("NQ")
    out = await fetch_trading_hours_async(ib, contract)
    assert out == []


@pytest.mark.asyncio
async def test_fetch_trading_hours_async_parses_trading_hours() -> None:
    """ContractDetails の tradingHours をパースして返す。"""
    from avionics.ib.schedule_scan import _contract_for_symbol, fetch_trading_hours_async

    today = date.today()
    raw = f"{today.strftime('%Y%m%d')}:0930-1600"
    details = MagicMock()
    details.tradingHours = raw
    ib = MagicMock()
    ib.reqContractDetailsAsync = AsyncMock(return_value=[details])
    contract = _contract_for_symbol("NQ")
    out = await fetch_trading_hours_async(ib, contract)
    assert len(out) == 1
    assert out[0].date_str == today.strftime("%Y%m%d")
    assert out[0].close_time == "1600"
