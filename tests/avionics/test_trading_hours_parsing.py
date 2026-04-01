"""schedule client/service 経由のパース正規化テスト。"""

from __future__ import annotations

from datetime import date

from avionics.ib.clients.schedule_client import IBScheduleClient
from avionics.ib.services.schedule_service import IBScheduleService


class _Detail:
    def __init__(self, trading: str, liquid: str = "", tz: str = "US/Eastern") -> None:
        self.tradingHours = trading
        self.liquidHours = liquid
        self.timeZoneId = tz


class _FakeIb:
    def __init__(self, details: list[_Detail]) -> None:
        self._details = details

    async def reqContractDetailsAsync(self, _contract):
        return self._details


def test_client_fetch_schedule_bundle_normalizes_end_date_prefix() -> None:
    raw = "20260325:0830-20260325:1600;20260326:0830-20260326:1600"
    client = IBScheduleClient(_FakeIb([_Detail(raw)]))
    bundle = __import__("asyncio").run(client.fetch_schedule_bundle(object()))
    out = bundle["trading_schedule"]
    assert out
    assert out[0].date_str == "20260325"
    assert out[0].sessions == ["0830-1600"]
    assert out[0].close_time == "1600"


def test_service_resolve_core_start() -> None:
    raw = "20260325:0830-20260325:1600"
    service = IBScheduleService(_FakeIb([_Detail(raw)]))
    picked = __import__("asyncio").run(
        service.resolve_core_start(
            symbol="NQ",
            ny_date=date(2026, 3, 25),
            contract_resolver=lambda _symbol: object(),
        )
    )
    assert picked is not None
    d, start, _tz = picked
    assert d == date(2026, 3, 25)
    assert start.hour == 8 and start.minute == 30


def test_service_resolve_core_session_returns_end() -> None:
    raw = "20260325:0830-20260325:1600"
    service = IBScheduleService(_FakeIb([_Detail(raw)]))
    picked = __import__("asyncio").run(
        service.resolve_core_session(
            symbol="NQ",
            ny_date=date(2026, 3, 25),
            contract_resolver=lambda _symbol: object(),
        )
    )
    assert picked is not None
    d, start, end, _tz = picked
    assert d == date(2026, 3, 25)
    assert start.hour == 8 and start.minute == 30
    assert end.hour == 16 and end.minute == 0


def test_service_resolve_core_start_re_raises_with_context_on_client_error() -> None:
    service = IBScheduleService(_FakeIb([]))
    with __import__("pytest").raises(ValueError, match="symbol=NQ"):
        __import__("asyncio").run(
            service.resolve_core_start(
                symbol="NQ",
                ny_date=date(2026, 3, 25),
                contract_resolver=lambda _symbol: object(),
            )
        )

