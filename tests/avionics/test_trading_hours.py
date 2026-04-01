"""
取引時間パース・スケジュール通知のテスト。
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from avionics.ib.clients.schedule_client import IBScheduleClient
from avionics.ib.services.schedule_service import IBScheduleService


class _Detail:
    def __init__(self, trading: str, liquid: str = "", tz: str = "US/Eastern") -> None:
        self.tradingHours = trading
        self.liquidHours = liquid
        self.timeZoneId = tz


class _FakeIb:
    def __init__(self, details):
        self._details = details

    async def reqContractDetailsAsync(self, _contract):
        return self._details


def test_client_fetch_trading_hours_empty_when_blank() -> None:
    client = IBScheduleClient(_FakeIb([_Detail("")]))
    with pytest.raises(ValueError, match="tradingHours field is empty"):
        asyncio.run(client.fetch_trading_hours(object()))


def test_client_fetch_trading_hours_single_day() -> None:
    raw = "20250310:0930-1600"
    client = IBScheduleClient(_FakeIb([_Detail(raw)]))
    out = asyncio.run(client.fetch_trading_hours(object()))
    assert len(out) == 1
    assert out[0].date_str == "20250310"
    assert out[0].sessions == ["0930-1600"]
    assert out[0].close_time == "1600"


def test_service_run_daily_schedule_scan_returns_messages() -> None:
    today = date.today().strftime("%Y%m%d")
    service = IBScheduleService(_FakeIb([_Detail(f"{today}:0930-1300")]))
    out = asyncio.run(service.run_daily_schedule_scan(["NQ"]))
    assert len(out) == 1
    assert out[0][0] == "NQ"
    assert isinstance(out[0][1], list)


@pytest.mark.asyncio
async def test_fetch_trading_hours_async_no_connection_raises_value_error() -> None:
    """接続失敗時は ValueError を送出する。"""
    ib = MagicMock()
    ib.reqContractDetailsAsync = AsyncMock(side_effect=ConnectionError())
    client = IBScheduleClient(ib)
    contract = client.contract_for_symbol("NQ")
    with pytest.raises(ValueError, match="failed to fetch contract details"):
        await client.fetch_trading_hours(contract)


@pytest.mark.asyncio
async def test_fetch_trading_hours_async_parses_trading_hours() -> None:
    """ContractDetails の tradingHours をパースして返す。"""
    today = date.today()
    raw = f"{today.strftime('%Y%m%d')}:0930-1600"
    details = MagicMock()
    details.tradingHours = raw
    ib = MagicMock()
    ib.reqContractDetailsAsync = AsyncMock(return_value=[details])
    client = IBScheduleClient(ib)
    contract = client.contract_for_symbol("NQ")
    out = await client.fetch_trading_hours(contract)
    assert len(out) == 1
    assert out[0].date_str == today.strftime("%Y%m%d")
    assert out[0].close_time == "1600"
