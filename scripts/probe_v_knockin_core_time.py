#!/usr/bin/env python3
"""
V因子復帰判定用: コアタイム開始の「当日取得」プローブ。

目的:
- IBKR の tradingHours（API）から
  - NQ/GC（先物）: コアタイム開始（ET）
  - VXN/GVZ（指数）: コアタイム開始（ET）
  を抽出できるか確認する。

出力:
- ET開始時刻（core start）と、JST（Asia/Tokyo）換算の開始時刻

用法:
  PYTHONPATH=src python scripts/probe_v_knockin_core_time.py
  PYTHONPATH=src python scripts/probe_v_knockin_core_time.py --host 127.0.0.1 --port 8888 --days 3
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable, Optional, Tuple


_root = Path(__file__).resolve().parent.parent
_scripts = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))


from avionics.calendar import JST_TZ, NY_TZ, convert_datetime, local_datetime_from_date_time


def _parse_session_start_hhmm(session: str) -> Optional[time]:
    """
    tradingHours parser の sessions から開始時刻（HH:MM）を抽出する。

    例:
      "0930-1600" -> 09:30
      "08:20-13:30" -> 08:20（万一の別形式にも対応）
    """
    s = session.strip()
    if not s:
        return None

    left = s.split("-")[0].strip()
    left = left.replace(":", "")
    if len(left) != 4 or not left.isdigit():
        return None

    hh = int(left[:2])
    mm = int(left[2:])
    return time(hh, mm)


def _pick_day_schedule_by_ny_date(schedule_list: Iterable[object], ny_date: date) -> Optional[object]:
    """
    DaySchedule（date_str=YYYYMMDD）から、NY日付一致のものを優先して選ぶ。
    """
    target = ny_date.strftime("%Y%m%d")
    lst = list(schedule_list)
    for d in lst:
        date_str = getattr(d, "date_str", None)
        if date_str == target:
            return d
    return lst[0] if lst else None


@dataclass(frozen=True)
class ProbeResult:
    symbol: str
    date_str: str
    tz_id: str
    core_start_local: time
    core_start_et: time
    core_start_jst: time


async def _probe_symbol(
    *,
    ib: object,
    symbol: str,
    contract_resolver: object,
    days: int,
    ny_today: date,
) -> Optional[ProbeResult]:
    """
    tradingHours から、最初のセッション開始を core start として抽出する。
    """
    contract = contract_resolver(symbol)
    raw_trading, raw_liquid, tz_id = await _fetch_hours_raw(ib, contract)

    from avionics.ib.trading_hours import core_start_from_hours_raw

    picked = core_start_from_hours_raw(raw_liquid or raw_trading, ny_date=ny_today)
    if picked is None:
        return None
    chosen_date, core_start_local = picked
    date_str = chosen_date.strftime("%Y%m%d")

    dt_local = local_datetime_from_date_time(d=chosen_date, t=core_start_local, tz_id=tz_id)
    dt_et = convert_datetime(dt_local, NY_TZ)
    dt_jst = convert_datetime(dt_local, JST_TZ)

    return ProbeResult(
        symbol=symbol,
        date_str=date_str,
        tz_id=tz_id or "",
        core_start_local=dt_local.timetz().replace(tzinfo=None),
        core_start_et=dt_et.timetz().replace(tzinfo=None),
        core_start_jst=dt_jst.timetz().replace(tzinfo=None),
    )


async def _fetch_hours_raw(ib: object, contract: object) -> Tuple[str, str, str]:
    """
    IB の reqContractDetails から tradingHours / liquidHours を取得する。
    取れない場合は空文字列。
    """
    try:
        details_list = await ib.reqContractDetailsAsync(contract)
    except Exception:
        return ("", "", "")
    if not details_list:
        return ("", "", "")
    details = details_list[0]
    trading = getattr(details, "tradingHours", None) or getattr(details, "trading_hours", None) or ""
    liquid = getattr(details, "liquidHours", None) or getattr(details, "liquid_hours", None) or ""
    tz_id = getattr(details, "timeZoneId", None) or getattr(details, "time_zone_id", None) or ""
    return (str(trading), str(liquid), str(tz_id))


def _parse_hours(raw: str) -> list[object]:
    from avionics.ib.trading_hours import parse_trading_hours
    return list(parse_trading_hours(raw))


def _core_start_from_sessions(sessions: Iterable[str]) -> Optional[time]:
    starts = [_parse_session_start_hhmm(s) for s in sessions]
    starts = [st for st in starts if st is not None]
    return min(starts) if starts else None


async def main() -> int:
    parser = argparse.ArgumentParser(description="V因子復帰判定: core time 開始の取得確認プローブ")
    parser.add_argument("--host", default="127.0.0.1", help="IB Gateway / TWS host")
    parser.add_argument("--port", type=int, default=4002, help="IB Gateway / TWS port")
    parser.add_argument("--client-id", type=int, default=3, help="IB API client id")
    parser.add_argument("--days", type=int, default=3, help="tradingHours を取る日数（表示用。APIの返却に依存）")
    args = parser.parse_args()

    from avionics.calendar import ny_date_now
    from avionics.ib import with_ib_connection
    from avionics.ib.fetcher import _contract_for_price, _contract_for_volatility

    ny_today = ny_date_now()

    symbols_futures = ["NQ", "GC"]
    symbols_indices = ["VXN", "GVZ"]

    futures_results: list[ProbeResult] = []
    indices_results: list[ProbeResult] = []

    async with with_ib_connection(
        args.host,
        args.port,
        client_id=args.client_id,
        timeout=30.0,
    ) as ib:
        for sym in symbols_futures:
            r = await _probe_symbol(
                ib=ib,
                symbol=sym,
                contract_resolver=_contract_for_price,
                days=args.days,
                ny_today=ny_today,
            )
            if r:
                futures_results.append(r)

        for sym in symbols_indices:
            r = await _probe_symbol(
                ib=ib,
                symbol=sym,
                contract_resolver=_contract_for_volatility,
                days=args.days,
                ny_today=ny_today,
            )
            if r:
                indices_results.append(r)

    def _fmt(results: list[ProbeResult]) -> str:
        lines = []
        for r in results:
            local = r.core_start_local.strftime("%H:%M")
            et = r.core_start_et.strftime("%H:%M")
            jst = r.core_start_jst.strftime("%H:%M")
            tz = r.tz_id or "?"
            lines.append(
                f"{r.symbol}: core_start local({tz}) {local} -> ET {et} / JST {jst} (tradeDate={r.date_str})"
            )
        return "\n".join(lines)

    print(f"NY today: {ny_today.isoformat()}")
    print("=== Futures (NQ/GC) tradingHours -> core start ===")
    print(_fmt(futures_results) if futures_results else "(no results)")
    print("=== Indices (VXN/GVZ) tradingHours -> core start ===")
    print(_fmt(indices_results) if indices_results else "(no results)")

    # 追加: raw も表示して確認できるようにする（当日判断用）
    print("\n=== Raw hours (tradingHours / liquidHours) ===")
    async with with_ib_connection(
        args.host,
        args.port,
        client_id=args.client_id,
        timeout=30.0,
    ) as ib:
        for sym in symbols_futures + symbols_indices:
            resolver = _contract_for_price if sym in symbols_futures else _contract_for_volatility
            trading, liquid, tz_id = await _fetch_hours_raw(ib, resolver(sym))
            print(f"\n[{sym}] tradingHours={trading}")
            print(f"[{sym}] liquidHours={liquid}")
            print(f"[{sym}] timeZoneId={tz_id}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

