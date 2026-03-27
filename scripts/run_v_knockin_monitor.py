#!/usr/bin/env python3
"""
V因子復帰（V1→V0）の 1h ノックイン監視ループ。

仕様（ユーザ指示 + SPEC）:
- 当日コアタイムは IB API（contract details の liquidHours + timeZoneId）から取得する
- 監視開始はコアタイム開始 + 15分（ディレイデータ想定）
- コアタイム開始後の「最初の完全な1h足」を利用する（足は00分区切り）
- 以降、ノックインするまで 1h 毎に判定する

起動:
  PYTHONPATH=src python scripts/run_v_knockin_monitor.py --host ib-gateway --port 8888
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


_root = Path(__file__).resolve().parent.parent
_scripts = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))


async def _sleep_until(target_utc: datetime) -> None:
    if target_utc.tzinfo is None:
        raise ValueError("_sleep_until requires tz-aware datetime")
    while True:
        now = datetime.now(timezone.utc)
        delta = (target_utc - now).total_seconds()
        if delta <= 0:
            return
        await asyncio.sleep(min(delta, 30.0))


async def main() -> int:
    parser = argparse.ArgumentParser(description="V復帰 1h ノックイン監視")
    parser.add_argument("--host", default=os.environ.get("IBKR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("IBKR_PORT", "4002")))
    parser.add_argument("--client-id", type=int, default=int(os.environ.get("IBKR_CLIENT_ID", "7")))
    parser.add_argument("--symbols", nargs="+", default=["NQ", "GC"])
    parser.add_argument("--delay-minutes", type=int, default=15, help="ディレイデータ想定の開始遅延（分）")
    parser.add_argument("--once", action="store_true", help="待機せず1回だけ判定して終了（デバッグ用）")
    args = parser.parse_args()

    from avionics.calendar import (
        JST_TZ,
        NY_TZ,
        ceil_to_next_hour,
        convert_datetime,
        local_datetime_from_date_time,
        ny_date_now,
    )
    from avionics.ib import with_ib_connection
    from avionics.ib.fetcher import IBRawFetcher, _contract_for_volatility
    from avionics.ib.trading_hours import core_session_from_hours_raw
    from cockpit.stack import build_cockpit_stack
    from notifications.telegram import send_telegram_message
    from store.db import get_connection
    from store.knockin_watch import list_pending_symbols, set_knocked_in

    ny_today = ny_date_now()

    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    conn = get_connection()
    try:
        pending = list_pending_symbols(conn, as_of=ny_today)
        if not pending:
            print(f"no pending knockin_watch rows for as_of={ny_today.isoformat()}; exiting")
            return 0
    finally:
        conn.close()

    async with with_ib_connection(args.host, args.port, client_id=args.client_id, timeout=30.0) as ib:
        fetcher = IBRawFetcher(ib)
        fc, _ = build_cockpit_stack(list(args.symbols))

        # コアタイム取得: VXN/GVZ（指数）の tradingHours/timeZoneId を利用する
        core_ref = "VXN"
        details_list = await ib.reqContractDetailsAsync(_contract_for_volatility(core_ref))
        if not details_list:
            raise RuntimeError(f"reqContractDetailsAsync returned empty list for {core_ref}")
        details = details_list[0]
        trading = str(getattr(details, "tradingHours", "") or getattr(details, "trading_hours", "") or "")
        tz_id = str(getattr(details, "timeZoneId", "") or getattr(details, "time_zone_id", "") or "")
        if not trading:
            raise RuntimeError(f"{core_ref} tradingHours is empty; cannot resolve core time")

        core = core_session_from_hours_raw(trading, ny_date=ny_today)
        if core is None:
            raise RuntimeError(f"Cannot parse core session from tradingHours for {ny_today}")
        trade_date, core_start_local, core_end_local = core

        dt_core_start_local = local_datetime_from_date_time(d=trade_date, t=core_start_local, tz_id=tz_id)
        dt_core_end_local = local_datetime_from_date_time(d=trade_date, t=core_end_local, tz_id=tz_id)

        dt_core_start_et = convert_datetime(dt_core_start_local, NY_TZ)
        dt_core_end_et = convert_datetime(dt_core_end_local, NY_TZ)
        dt_core_start_jst = convert_datetime(dt_core_start_local, JST_TZ)
        dt_core_end_jst = convert_datetime(dt_core_end_local, JST_TZ)

        # 最初の完全な 1h 足: core_start を次の HH:00 に切り上げ、その 1h 後が bar_end
        start_boundary = ceil_to_next_hour(dt_core_start_local)
        first_bar_end = start_boundary + timedelta(hours=1)
        first_eval = first_bar_end + timedelta(minutes=int(args.delay_minutes))

        # 判定を止める時刻（コアタイム終了 + 15分）
        end_eval = dt_core_end_local + timedelta(minutes=int(args.delay_minutes))
        end_eval_utc = end_eval.astimezone(timezone.utc)

        print(
            f"core_time({core_ref} tradingHours): "
            f"local({tz_id or '?'}) {dt_core_start_local.isoformat()}–{dt_core_end_local.isoformat()} | "
            f"ET {dt_core_start_et.time().strftime('%H:%M')}–{dt_core_end_et.time().strftime('%H:%M')} | "
            f"JST {dt_core_start_jst.time().strftime('%H:%M')}–{dt_core_end_jst.time().strftime('%H:%M')}"
        )
        print(f"first_eval(local)={first_eval.isoformat()} end_eval(local)={end_eval.isoformat()}")

        async def _eval_once() -> Optional[tuple[str, str]]:
            await fc.refresh(fetcher, ny_today, list(args.symbols))
            bundle = fc.get_last_bundle()
            if bundle is None:
                raise RuntimeError("fc.refresh did not set bundle")
            for sym in pending:
                vs = bundle.volatility_signals.get(sym)
                if vs and vs.v1_to_v0_knock_in_ok:
                    # 成立した 1h 足の bar_end（ISO文字列）をそのまま保存する
                    return (sym, vs.knock_in_bar_end or "")
            return None

        if args.once:
            hit = await _eval_once()
            print(f"knock_in_hit={hit}")
            return 0

        next_eval = first_eval
        while True:
            now_utc = datetime.now(timezone.utc)
            if end_eval_utc <= now_utc:
                print("core_time ended without knock-in")
                return 0

            # 次の評価時刻まで待つ
            await _sleep_until(next_eval.astimezone(timezone.utc))
            hit = await _eval_once()
            if hit:
                hit_sym, hit_bar_end = hit
                msg = f"✅ V knock-in detected for {hit_sym} (as_of={ny_today})"
                print(msg)
                # DB 更新
                conn2 = get_connection()
                try:
                    set_knocked_in(conn2, as_of=ny_today, symbol=hit_sym, bar_end_iso=hit_bar_end)
                finally:
                    conn2.close()
                if token and chat_id:
                    send_telegram_message(token=token, chat_id=chat_id, text=msg, timeout=20.0)
                return 0
            next_eval = next_eval + timedelta(hours=1)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

