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
from datetime import date
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

    from cockpit.stack import build_cockpit_stack
    from avionics.ib_data import IBDataFetcher
    from avionics.Instruments import FactorsConfigError, get_v_thresholds, load_factors_config

    try:
        from ib_async import IB
    except ImportError:
        print("ib_async がインストールされていません: pip install ib_async", file=sys.stderr)
        return 1

    # FC と Engine は同一 symbols で build_cockpit_stack で取得（本スクリプトは FC のみ使用）
    fc, _engines = build_cockpit_stack(args.symbols)
    try:
        config = load_factors_config()
        print("FlightController: config/factors.toml に基づき因子を登録しました。")
    except FactorsConfigError:
        config = None
        print("FlightController: 因子設定なしで起動（config/factors.toml なし）")

    # IB 接続
    ib = IB()
    try:
        await ib.connectAsync(host=args.host, port=args.port, clientId=args.client_id)
    except Exception as e:
        print(f"IB 接続失敗: {e}", file=sys.stderr)
        return 1

    try:
        from util import ny_date_now
        fetcher = IBDataFetcher(ib)
        as_of = ny_date_now()  # バー日付（NY Trade Date）と整合
        v_recovery_params = None
        if config:
            try:
                v_recovery_params = {
                    s: get_v_thresholds(config, s)["high_mid"]
                    for s in args.symbols
                }
            except (FactorsConfigError, KeyError):
                pass
        print(f"SignalBundle 取得中（as_of={as_of}, symbols={args.symbols}）...")
        bundle, _ = await fetcher.fetch_signal_bundle(
            as_of=as_of,
            price_symbols=args.symbols,
            liquidity_credit_symbol="HYG",
            liquidity_tip=True,
            base_density=args.base_density,
            v_recovery_params=v_recovery_params,
        )
        await fc.update_all(signal_bundle=bundle)

        if args.breakdown:
            from avionics.Instruments.signals import format_signal_bundle_breakdown
            print(format_signal_bundle_breakdown(bundle))
            print("---")

        print("--- FlightController 計器シグナル ---")
        from reports.format_fc_signal import build_reason, get_raw_metrics
        signal = await fc.get_flight_controller_signal(bundle=bundle)
        for sym in args.symbols:
            sym_sig = signal.by_symbol.get(sym)
            if sym_sig is None:
                continue
            mode_str = {0: "Boost", 1: "Cruise", 2: "Emergency"}.get(sym_sig.throttle_level, "?")
            reason = build_reason(sym_sig.icl, signal.scl, signal.lcl)
            raw_metrics = get_raw_metrics(fc.mapping, sym)
            print(f"  {sym}: throttle={sym_sig.throttle_level} ({mode_str})")
            print(f"        reason={reason}")
            print(f"        is_critical={sym_sig.is_critical}, raw_metrics={raw_metrics}")
        return 0
    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
