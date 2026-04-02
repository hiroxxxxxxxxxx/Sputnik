from __future__ import annotations

import re
from datetime import date, time, timedelta
from typing import Any, List, Optional, Tuple

from ..clients.schedule_client import IBScheduleClient
from ..models.schedule import DaySchedule
from ..models.schedule_alert import ScheduleAlert
from ..models.schedule_scan_row import ScheduleScanRow


def _pick_schedule_for_date(
    schedule_list: List[DaySchedule], ny_date: date
) -> DaySchedule:
    return next(schedule for schedule in schedule_list if schedule.as_date == ny_date)


def core_start_from_schedule(
    schedule_list: List[DaySchedule], *, ny_date: date
) -> tuple[date, time]:
    chosen = _pick_schedule_for_date(schedule_list, ny_date)
    return (chosen.as_date, min(chosen.start_times))


def core_session_from_schedule(
    schedule_list: List[DaySchedule], *, ny_date: date
) -> Tuple[date, time, time]:
    chosen = _pick_schedule_for_date(schedule_list, ny_date)
    return (chosen.as_date, min(chosen.start_times), max(chosen.end_times))


def _is_closed_day(sched: DaySchedule) -> bool:
    return bool(sched.sessions) and all(s == "CLOSED" for s in sched.sessions)


def _normal_close_hhmm_for_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s in ("GC", "MGC"):
        return "1700"
    return "1600"


def exchange_tz_short_label(timezone_id: str) -> str:
    tid = (timezone_id or "").lower()
    if "chicago" in tid or "central" in tid:
        return "CT"
    return "ET"


def build_schedule_alerts(
    schedule_list: List[DaySchedule],
    days: int = 3,
    normal_close_et: str = "1600",
    tz_label: str = "ET",
    *,
    today_anchor: Optional[date] = None,
) -> List[ScheduleAlert]:
    normal_close = re.sub(r"[:\s]", "", normal_close_et).strip()
    if len(normal_close) != 4 or not normal_close.isdigit():
        raise ValueError(f"normal_close_et must be 4 digit HHMM: {normal_close_et!r}")
    by_date = {s.date_str: s for s in schedule_list}
    today = today_anchor if today_anchor is not None else date.today()
    alerts: List[ScheduleAlert] = []
    today_key = today.strftime("%Y%m%d")
    today_sched = by_date.get(today_key)
    if today_sched and _is_closed_day(today_sched):
        today_close = normal_close
    elif today_sched and (today_sched.close_time or "").strip():
        today_close = re.sub(r"[:\s]", "", str(today_sched.close_time)).strip()
    else:
        today_close = normal_close
    if len(today_close) != 4 or not today_close.isdigit():
        today_close = normal_close

    for i in range(1, days):
        d = today + timedelta(days=i)
        key = d.strftime("%Y%m%d")
        sched = by_date.get(key)
        if not sched:
            alerts.append(
                ScheduleAlert(
                    kind="missing_schedule_day",
                    relative_offset=i,
                    trade_date_key=key,
                )
            )
            continue

        if _is_closed_day(sched):
            alerts.append(
                ScheduleAlert(
                    kind="closed_day",
                    relative_offset=i,
                    trade_date_key=key,
                )
            )
            continue

        day_close = re.sub(r"[:\s]", "", str(sched.close_time or "")).strip()
        if len(day_close) != 4 or not day_close.isdigit():
            raise ValueError(
                f"parsed schedule has non-closed day without 4-digit close_time: "
                f"date={key!r} close_time={sched.close_time!r}"
            )
        day_close_val = int(day_close)
        today_close_val = int(today_close) if len(today_close) == 4 and today_close.isdigit() else int(normal_close)

        if i == 1:
            if day_close < normal_close:
                alerts.append(
                    ScheduleAlert(
                        kind="shortened_close",
                        relative_offset=i,
                        trade_date_key=key,
                        close_hhmm=day_close,
                        tz_label=tz_label,
                    )
                )
            if abs(day_close_val - today_close_val) == 100:
                alerts.append(
                    ScheduleAlert(
                        kind="dst_shift_1h",
                        relative_offset=i,
                        trade_date_key="",
                    )
                )
            elif abs(day_close_val - today_close_val) in (2300, 900):
                alerts.append(
                    ScheduleAlert(
                        kind="dst_shift_other",
                        relative_offset=i,
                        trade_date_key="",
                    )
                )
    return alerts


class IBScheduleService:
    """取引時間スキャンのユースケースを提供するサービス。"""

    def __init__(self, ib: Any) -> None:
        self._client = IBScheduleClient(ib)

    async def run_daily_schedule_scan(
        self,
        symbols: List[str],
        contract_resolver: Optional[Any] = None,
    ) -> List[ScheduleScanRow]:
        resolve = (
            contract_resolver if contract_resolver is not None else self._client.contract_for_symbol
        )
        results: List[ScheduleScanRow] = []
        for symbol in symbols:
            try:
                contract = resolve(symbol)
                bundle = await self._client.fetch_schedule_bundle(contract)
                trading_schedule: List[DaySchedule] = bundle["trading_schedule"]
                liquid_schedule: List[DaySchedule] = bundle["liquid_schedule"]
                schedule_list = (
                    liquid_schedule if liquid_schedule else trading_schedule
                )
                used_liquid = bool(liquid_schedule)
                tz_hint = exchange_tz_short_label(str(bundle["timezone_id"]))
                normal = _normal_close_hhmm_for_symbol(symbol)
                alert_list = build_schedule_alerts(
                    schedule_list,
                    days=3,
                    normal_close_et=normal,
                    tz_label=tz_hint,
                )
                results.append(
                    ScheduleScanRow(
                        symbol=symbol,
                        alerts=alert_list,
                        trading_hours_raw=bundle["trading_hours_raw"],
                        liquid_hours_raw=bundle["liquid_hours_raw"],
                        timezone_id=str(bundle["timezone_id"]),
                        scan_used_liquid=used_liquid,
                        fetch_error=None,
                    )
                )
            except Exception as exc:
                results.append(
                    ScheduleScanRow(
                        symbol=symbol,
                        alerts=[],
                        trading_hours_raw="",
                        liquid_hours_raw="",
                        timezone_id="",
                        scan_used_liquid=False,
                        fetch_error=f"{type(exc).__name__}: {exc}",
                    )
                )
        return results

    async def resolve_core_session(
        self,
        *,
        symbol: str,
        ny_date: date,
        contract_resolver: Optional[Any] = None,
        prefer_liquid_hours: bool = True,
    ) -> tuple[date, time, time, str]:
        resolve = (
            contract_resolver if contract_resolver is not None else self._client.contract_for_symbol
        )
        contract = resolve(symbol)
        try:
            bundle = await self._client.fetch_schedule_bundle(contract)
        except ValueError as exc:
            raise ValueError(
                "failed to resolve schedule bundle "
                f"(symbol={symbol}, ny_date={ny_date.isoformat()}, prefer_liquid_hours={prefer_liquid_hours}): {exc}"
            ) from exc
        trading_schedule: List[DaySchedule] = bundle["trading_schedule"]
        liquid_schedule: List[DaySchedule] = bundle["liquid_schedule"]
        tz_id = str(bundle["timezone_id"])
        schedule = (
            liquid_schedule
            if prefer_liquid_hours and liquid_schedule
            else trading_schedule
        )
        d, start, end = core_session_from_schedule(schedule, ny_date=ny_date)
        return (d, start, end, tz_id)

    async def resolve_core_start(
        self,
        *,
        symbol: str,
        ny_date: date,
        contract_resolver: Optional[Any] = None,
        prefer_liquid_hours: bool = True,
    ) -> tuple[date, time, str]:
        resolve = (
            contract_resolver if contract_resolver is not None else self._client.contract_for_symbol
        )
        contract = resolve(symbol)
        try:
            bundle = await self._client.fetch_schedule_bundle(contract)
        except ValueError as exc:
            raise ValueError(
                "failed to resolve schedule bundle "
                f"(symbol={symbol}, ny_date={ny_date.isoformat()}, prefer_liquid_hours={prefer_liquid_hours}): {exc}"
            ) from exc
        trading_schedule: List[DaySchedule] = bundle["trading_schedule"]
        liquid_schedule: List[DaySchedule] = bundle["liquid_schedule"]
        tz_id = str(bundle["timezone_id"])
        schedule = (
            liquid_schedule
            if prefer_liquid_hours and liquid_schedule
            else trading_schedule
        )
        d, start = core_start_from_schedule(schedule, ny_date=ny_date)
        return (d, start, tz_id)
