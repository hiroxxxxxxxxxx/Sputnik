"""schedule client/service 経由のパース正規化テスト。"""

from __future__ import annotations

from datetime import date, time, timedelta

from avionics.ib.clients.schedule_client import IBScheduleClient
from avionics.ib.models.schedule import DaySchedule
from avionics.ib.services.schedule_service import (
    IBScheduleService,
    build_schedule_alerts,
    exchange_tz_short_label,
)


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
    assert bundle["trading_hours_raw"] == raw
    assert bundle["liquid_hours_raw"] == ""


def test_fetch_schedule_bundle_returns_liquid_raw_when_present() -> None:
    tr = "20260325:0830-20260325:1600"
    liq = "20260325:1700-20260326:1600"
    client = IBScheduleClient(_FakeIb([_Detail(tr, liquid=liq)]))
    bundle = __import__("asyncio").run(client.fetch_schedule_bundle(object()))
    assert bundle["trading_hours_raw"] == tr
    assert bundle["liquid_hours_raw"] == liq
    assert len(bundle["liquid_schedule"]) >= 1


def test_build_schedule_alerts_detects_closed_tomorrow() -> None:
    anchor = date(2026, 4, 2)
    t0 = anchor.strftime("%Y%m%d")
    t1 = (anchor + timedelta(days=1)).strftime("%Y%m%d")
    t2 = (anchor + timedelta(days=2)).strftime("%Y%m%d")
    schedules = [
        DaySchedule(t0, ["0930-1600"], "1600", [time(9, 30)], [time(16, 0)]),
        DaySchedule(t1, ["CLOSED"], "", [], []),
        DaySchedule(t2, ["0930-1600"], "1600", [time(9, 30)], [time(16, 0)]),
    ]
    alerts = build_schedule_alerts(
        schedules,
        days=3,
        normal_close_et="1600",
        tz_label="ET",
        today_anchor=anchor,
    )
    closed = [a for a in alerts if a.kind == "closed_day"]
    assert closed and closed[0].trade_date_key == t1


def test_exchange_tz_short_label_chicago_vs_eastern() -> None:
    assert exchange_tz_short_label("US/Central") == "CT"
    assert exchange_tz_short_label("America/Chicago") == "CT"
    assert exchange_tz_short_label("US/Eastern") == "ET"


def test_build_schedule_alerts_gc_1600_is_shortened_vs_1700_baseline() -> None:
    anchor = date(2026, 4, 2)
    t0 = anchor.strftime("%Y%m%d")
    t1 = (anchor + timedelta(days=1)).strftime("%Y%m%d")
    schedules = [
        DaySchedule(t0, ["0930-1700"], "1700", [time(9, 30)], [time(17, 0)]),
        DaySchedule(t1, ["0930-1600"], "1600", [time(9, 30)], [time(16, 0)]),
    ]
    alerts = build_schedule_alerts(
        schedules,
        days=2,
        normal_close_et="1700",
        tz_label="ET",
        today_anchor=anchor,
    )
    short = [a for a in alerts if a.kind == "shortened_close"]
    assert short and short[0].close_hhmm == "1600"


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


def test_format_schedule_scan_fetch_error_includes_exception_detail() -> None:
    from avionics.ib.models.schedule_scan_row import ScheduleScanRow
    from reports.format_schedule_scan import format_schedule_scan

    row = ScheduleScanRow(
        symbol="NQ",
        alerts=[],
        trading_hours_raw="",
        liquid_hours_raw="",
        timezone_id="",
        scan_used_liquid=False,
        fetch_error="ValueError: boom",
    )
    text = format_schedule_scan([row])
    assert "失敗" in text
    assert "ValueError: boom" in text


def test_format_schedule_scan_renders_closed_day_with_liquid_source() -> None:
    from avionics.ib.models.schedule_alert import ScheduleAlert
    from avionics.ib.models.schedule_scan_row import ScheduleScanRow
    from reports.format_schedule_scan import format_schedule_scan

    row = ScheduleScanRow(
        symbol="NQ",
        alerts=[
            ScheduleAlert(
                kind="closed_day",
                relative_offset=1,
                trade_date_key="20260403",
            )
        ],
        trading_hours_raw="x",
        liquid_hours_raw="y",
        timezone_id="US/Eastern",
        scan_used_liquid=True,
        fetch_error=None,
    )
    text = format_schedule_scan([row])
    assert "終日休場" in text
    assert "liquidHours" in text
    assert "判定スケジュール: liquidHours" in text


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

