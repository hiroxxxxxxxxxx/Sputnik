"""
Layer 2 Process: RawMarketSnapshot と as_of から SignalBundle を組み立てる。

API（取得）は知らず、Raw が渡される前提で compute_* を呼ぶだけ。
定義書「4-2 情報の階層構造」・案B B-2 参照。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from .data.raw_market_snapshot import RawMarketSnapshot
from .data.signals import (
    AltitudeRegime,
    LiquiditySignals,
    SignalBundle,
    VolatilitySignal,
)


@dataclass(frozen=True)
class BundleBuildOptions:
    """
    FC 構築時に注入する、build_signal_bundle 用のオプション。
    refresh 時に FC がこの値を使って bundle を組み立てる。
    """

    liquidity_credit_hyg_symbol: str
    liquidity_credit_lqd_symbol: str
    altitude: AltitudeRegime
    liquidity_tip_symbol: Optional[str] = None
    base_density: float = 1.0
    s_baseline_by_symbol: Optional[Dict[str, float]] = None
    account: str = ""
    volatility_symbols: Optional[Dict[str, str]] = None
    v_recovery_params: Optional[Dict[str, dict]] = None
from .compute import (
    compute_capital_signals_from_snapshot,
    compute_liquidity_signals_credit_from_snapshot,
    compute_liquidity_signals_tip_from_snapshot,
    compute_price_signals_from_snapshot,
    compute_volatility_signal_from_snapshot,
)


def build_signal_bundle(
    snapshot: RawMarketSnapshot,
    as_of: date,
    price_symbols: List[str],
    *,
    liquidity_credit_hyg_symbol: str,
    liquidity_credit_lqd_symbol: str,
    liquidity_tip_symbol: Optional[str] = None,
    altitude: AltitudeRegime,
    v_recovery_params: Optional[Dict[str, dict]] = None,
) -> SignalBundle:
    """
    RawMarketSnapshot と as_of から compute_* を呼び、SignalBundle を組み立てて返す。

    :param snapshot: Layer 1 のスナップショット（RawMarketSnapshot）。
    :param as_of: 清算値の「当日」バー検索に使う基準日。
    :param price_symbols: P/T 用銘柄リスト（例: ["NQ", "GC"]）。
    :param liquidity_credit_hyg_symbol: C因子主系列（例: "HYG"）。必須。
    :param liquidity_credit_lqd_symbol: C因子副系列（例: "LQD"）。必須。
    :param liquidity_tip_symbol: R因子用系列（例: "TIP"）。None なら取得しない。
    :param altitude: V/C/R 共通の高度設定。
    :param v_recovery_params: 銘柄→V因子の高度スライス（V1_off, V2_off 等）。
    """
    price_signals = {
        sym: compute_price_signals_from_snapshot(snapshot, sym, as_of)
        for sym in price_symbols
    }

    vol_signals: Dict[str, VolatilitySignal] = {}
    for sym in price_symbols:
        th = v_recovery_params.get(sym) if v_recovery_params else None
        v1_off = float(th["V1_off"]) if th and "V1_off" in th else None
        v2_off = float(th["V2_off"]) if th and "V2_off" in th else None
        vol_signals[sym] = compute_volatility_signal_from_snapshot(
            snapshot,
            sym,
            as_of,
            altitude,
            v1_off_threshold=v1_off,
            v2_off_threshold=v2_off,
        )

    cap_signals = compute_capital_signals_from_snapshot(snapshot, as_of)

    liquidity_credit_hyg = compute_liquidity_signals_credit_from_snapshot(
        snapshot, liquidity_credit_hyg_symbol, as_of, altitude
    )
    liquidity_credit_lqd = compute_liquidity_signals_credit_from_snapshot(
        snapshot, liquidity_credit_lqd_symbol, as_of, altitude
    )

    liquidity_tip_sig: Optional[LiquiditySignals] = None
    if liquidity_tip_symbol:
        liquidity_tip_sig = compute_liquidity_signals_tip_from_snapshot(
            snapshot, as_of, altitude
        )

    return SignalBundle(
        price_signals=price_signals,
        volatility_signals=vol_signals,
        liquidity_credit_hyg=liquidity_credit_hyg,
        liquidity_credit_lqd=liquidity_credit_lqd,
        liquidity_tip=liquidity_tip_sig,
        capital_signals=cap_signals,
    )
