from __future__ import annotations

import re
from datetime import date, time, timedelta
from typing import Any, List, Optional, Tuple

from ..clients.schedule_client import IBScheduleClient
from ..models.schedule import DaySchedule


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


def check_upcoming_schedule(
    schedule_list: List[DaySchedule],
    days: int = 3,
    normal_close_et: str = "1600",
) -> List[str]:
    normal_close = re.sub(r"[:\s]", "", normal_close_et).strip()
    if len(normal_close) != 4 or not normal_close.isdigit():
        normal_close = "1600"
    by_date = {s.date_str: s for s in schedule_list}
    today = date.today()
    messages: List[str] = []
    today_key = today.strftime("%Y%m%d")
    today_sched = by_date.get(today_key)
    today_close = (today_sched.close_time if today_sched else "1600") or "1600"
    today_close = re.sub(r"[:\s]", "", today_close).strip()
    if len(today_close) != 4 or not today_close.isdigit():
        today_close = "1600"

    for i in range(1, days):
        d = today + timedelta(days=i)
        key = d.strftime("%Y%m%d")
        sched = by_date.get(key)
        if not sched:
            if i == 1:
                messages.append("⚠️ 明日は取引所休場のため、システム監視をスキップすることを推奨します。")
            else:
                day_label = "明後日" if i == 2 else f"{i}日後"
                messages.append(f"⚠️ {day_label}（{key}）はスケジュールに含まれていません。休場の可能性があります。")
            continue

        day_close = re.sub(r"[:\s]", "", str(sched.close_time or "")).strip()
        if len(day_close) != 4 or not day_close.isdigit():
            day_close = "1600"
        day_close_val = int(day_close) if len(day_close) == 4 and day_close.isdigit() else 1600
        today_close_val = int(today_close) if today_close.isdigit() else 1600

        if i == 1:
            if day_close < normal_close:
                messages.append(
                    f"⚠️ 明日は短縮営業です（終了: {day_close[:2]}:{day_close[2:]} ET）。"
                    "1時間足監視はスキップすることを推奨します。"
                )
            if abs(day_close_val - today_close_val) == 100:
                messages.append(
                    "⏰ 明日から米国時間（夏時間/冬時間）が切り替わります。"
                    "日本時間の日次判定・監視開始時刻が1時間スライドします。"
                )
            elif abs(day_close_val - today_close_val) in (2300, 900):
                messages.append(
                    "⏰ 明日から米国時間が切り替わります。"
                    "日次判定・監視開始時刻の見直しを推奨します。"
                )
    return messages


class IBScheduleService:
    """取引時間スキャンのユースケースを提供するサービス。"""

    def __init__(self, ib: Any) -> None:
        self._client = IBScheduleClient(ib)

    async def run_daily_schedule_scan(
        self,
        symbols: List[str],
        contract_resolver: Optional[Any] = None,
    ) -> List[Tuple[str, List[str]]]:
        resolve = (
            contract_resolver if contract_resolver is not None else self._client.contract_for_symbol
        )
        results: List[Tuple[str, List[str]]] = []
        for symbol in symbols:
            try:
                contract = resolve(symbol)
                schedule_list = await self._client.fetch_trading_hours(contract)
                messages = check_upcoming_schedule(schedule_list, days=3)
                results.append((symbol, messages))
            except Exception:
                results.append((symbol, ["取引時間の取得に失敗しました。"]))
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
