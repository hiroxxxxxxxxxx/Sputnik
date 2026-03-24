#!/usr/bin/env python3
"""
IB 接続 → SignalBundle 取得 → Cockpit 更新 → 計器シグナル表示の一連フローを実行するサンプル。

用法:
  PYTHONPATH=src python scripts/run_cockpit_with_ib.py [--host HOST] [--port PORT] [--client-id ID]
  (IB Gateway / TWS はあらかじめ起動し API 有効にしておく)

config/factors.toml がある場合は因子を登録し、ない場合は Cockpit のみでデータ取得までを表示する。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# プロジェクトルートと scripts を path に追加
_root = Path(__file__).resolve().parent.parent
_scripts = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))


async def main() -> int:
    parser = argparse.ArgumentParser(description="IB から FlightController 用データを取得し計器シグナルを表示する")
    parser.add_argument(
        "--host",
        default=os.environ.get("IBKR_HOST", "127.0.0.1"),
        help="IB Gateway / TWS のホスト（環境変数 IBKR_HOST で上書き可）",
    )
    _port_env = os.environ.get("IBKR_PORT", "")
    _default_port = int(_port_env) if _port_env.isdigit() else 4002
    parser.add_argument(
        "--port",
        type=int,
        default=_default_port,
        help="API ポート（環境変数 IBKR_PORT で上書き可。TWS=7497, Gateway=4002）",
    )
    parser.add_argument("--client-id", type=int, default=1, help="API クライアント ID")
    parser.add_argument("--symbols", nargs="+", default=["NQ", "GC"], help="価格銘柄（例: NQ GC）")
    parser.add_argument("--base-density", type=float, default=1.0, help="証拠金 base_density")
    parser.add_argument("--breakdown", action="store_true", help="各因子の入力となる Layer 2 シグナル内訳を表示")
    args = parser.parse_args()

    try:
        from avionics.ib import with_ib_fetcher
    except ImportError:
        print("ib_async がインストールされていません: pip install ib_async", file=sys.stderr)
        return 1

    from avionics.Instruments import FactorsConfigError, load_factors_config
    from cockpit.stack import build_cockpit_stack
    from util import ny_date_now

    fc, _engines = build_cockpit_stack(args.symbols)
    try:
        load_factors_config()
        print("FlightController: config/factors.toml に基づき因子を登録しました。")
    except FactorsConfigError:
        print("FlightController: 因子設定なしで起動（config/factors.toml なし）")

    try:
        async with with_ib_fetcher(
            args.host,
            args.port,
            client_id=args.client_id,
            timeout=75.0,
        ) as fetcher:
            as_of = ny_date_now()
            print(f"取得中（as_of={as_of}, symbols={args.symbols}）...")
            await fc.refresh(fetcher, as_of, args.symbols)
            bundle = fc.get_last_bundle()

            if args.breakdown and bundle:
                from reports.format_signal_breakdown import format_signal_breakdown
                print(format_signal_breakdown(bundle))
                print("---")

            print("--- FlightController 計器シグナル ---")
            signal = await fc.get_flight_controller_signal()
            for sym in args.symbols:
                if sym not in signal.icl_by_symbol:
                    continue
                throttle = signal.throttle_level(sym)
                mode_str = {0: "Boost", 1: "Cruise", 2: "Emergency"}.get(throttle, "?")
                reason = signal.reason(sym)
                raw_metrics = signal.get_factor_levels(sym)
                print(f"  {sym}: throttle={throttle} ({mode_str})")
                print(f"        reason={reason}")
                print(f"        is_critical={signal.any_critical}, raw_metrics={raw_metrics}")
        return 0
    except Exception as e:
        print(f"IB 接続失敗: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
