#!/usr/bin/env python3
"""
NY クローズ後の日次ジョブ: IB から Raw を取得し FC を更新して ``signal_daily`` に 1 行 upsert する。

計画書 ``docs/plans/TODO.md``（SQLite 関連項目）参照。
cron / systemd / EventBridge 等で **1 日 1 回**（NY RTH 終了後）だけ実行すること。

用法:
  PYTHONPATH=src python scripts/run_daily_signal_persist.py [--host HOST] [--port PORT] [--as-of YYYY-MM-DD]

``--as-of`` は検証・再実行用。省略時は ``as_of_for_daily_signal_persist()`` に従う。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_scripts = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))


async def main() -> int:
    parser = argparse.ArgumentParser(description="日次 signal_daily を SQLite に保存（NY クローズ後）")
    parser.add_argument(
        "--host",
        default=os.environ.get("IBKR_HOST", "127.0.0.1"),
        help="IB Gateway / TWS のホスト",
    )
    _port_env = os.environ.get("IBKR_PORT", "")
    _default_port = int(_port_env) if _port_env.isdigit() else 4002
    parser.add_argument("--port", type=int, default=_default_port, help="API ポート")
    parser.add_argument("--client-id", type=int, default=1, help="API クライアント ID")
    parser.add_argument("--symbols", nargs="+", default=["NQ", "GC"], help="価格銘柄")
    parser.add_argument(
        "--skip-telegram",
        action="store_true",
        help="Telegram 送信をスキップ（TELEGRAM_TOKEN / TELEGRAM_CHAT_ID が未設定でもこのフラグは無視）",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="保存対象日 YYYY-MM-DD（省略時は NY 時刻に基づき自動決定）",
    )
    args = parser.parse_args()

    try:
        from avionics.ib import with_ib_fetcher
    except ImportError:
        print("ib_async がインストールされていません: pip install ib_async", file=sys.stderr)
        return 1

    from avionics.factors.factors_config import FactorsConfigError, load_factors_config
    from avionics.factors.factors_config import get_v_thresholds
    from avionics.calendar import as_of_for_daily_signal_persist, next_ny_business_day
    from cockpit.stack import build_cockpit_stack
    from store.db import get_connection
    from store.signal_daily import upsert_signal_daily
    from store.state import (
        read_altitude_regime,
        read_s_factor_baseline,
        read_target_futures,
    )
    from store.knockin_watch import create_watch
    from notifications.telegram import send_telegram_message
    from reports.format_daily_report import format_daily_report

    try:
        config = load_factors_config()
    except FactorsConfigError:
        print("config/factors.toml が必要です。", file=sys.stderr)
        return 1

    as_of_resolved: date
    if args.as_of:
        as_of_resolved = date.fromisoformat(args.as_of)
    else:
        as_of_resolved = as_of_for_daily_signal_persist()

    conn = get_connection()
    try:
        altitude = read_altitude_regime(conn)
        target_base_by_symbol = read_target_futures(conn)
        s_baseline_by_symbol = read_s_factor_baseline(conn)
        fc, _engines = build_cockpit_stack(
            args.symbols,
            altitude=altitude,
            s_baseline_by_symbol=s_baseline_by_symbol,
        )
        async with with_ib_fetcher(
            args.host,
            args.port,
            client_id=args.client_id,
            timeout=120.0,
        ) as fetcher:
            used = as_of_resolved
            await fc.refresh(fetcher, used, list(args.symbols), altitude=altitude)
            signal = await fc.get_flight_controller_signal()
            upsert_signal_daily(conn, as_of=used, signal=signal)

            # V 1h ノックイン監視日のレコード作成（監視が必要な銘柄だけ）
            # 監視日は「直近セッション日 used の Step1 成立」→「次営業日」に作る。
            bundle = fc.get_last_bundle()
            if bundle is None:
                raise RuntimeError("run_daily_signal_persist: fc.refresh did not set bundle")
            watch_day = next_ny_business_day(used)

            for sym in ("NQ", "GC"):
                if sym not in list(args.symbols):
                    continue
                vs = bundle.volatility_signals.get(sym)
                if vs is None:
                    continue
                alt = fc.last_altitude_regime
                if alt is None:
                    raise RuntimeError("run_daily_signal_persist: last_altitude_regime unset")
                required_days = int(get_v_thresholds(config, sym)[alt]["V1_confirm_days"])
                v_lv = int(signal.nq_v) if sym == "NQ" else int(signal.gc_v)
                step1_ok = vs.recovery_confirm_satisfied_days_v1_off >= required_days
                if v_lv == 1 and step1_ok and not (vs.v1_to_v0_knock_in_ok is True):
                    create_watch(conn, as_of=watch_day, symbol=sym)

            report_text = await format_daily_report(
                fc,
                list(args.symbols),
                target_base_by_symbol=target_base_by_symbol,
                as_of=used,
            )
            if not args.skip_telegram:
                token = os.environ.get("TELEGRAM_TOKEN", "").strip()
                chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
                if token and chat_id:
                    ok = send_telegram_message(
                        token=token,
                        chat_id=chat_id,
                        text=report_text[:3900],  # Telegram の上限回避
                        timeout=20.0,
                    )
                    if not ok:
                        print("Telegram send failed.", file=sys.stderr)
                else:
                    print("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 未設定のため Telegram 送信はスキップ。")

        print(f"signal_daily upsert + daily report generation 完了 as_of={used}")
        return 0
    except Exception as e:
        print(f"失敗: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
