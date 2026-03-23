"""
Layer 2 Process: RawDataProvider と as_of から SignalBundle を組み立てる。

API（取得）は知らず、Raw が渡される前提で compute_* を呼ぶだけ。
定義書「4-2 情報の階層構造」・案B B-2 参照。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Union

from ...data.raw import RawDataProvider
from ...data.raw_market_snapshot import RawMarketSnapshot, cached_raw_data_provider_from_snapshot
from ...data.signals import (
    AltitudeRegime,
    CapitalSignals,
    LiquiditySignals,
    PriceSignals,
    SignalBundle,
    VolatilitySignal,
)
from .compute import (
    compute_capital_signals,
    compute_liquidity_signals_credit,
    compute_liquidity_signals_tip,
    compute_price_signals,
    compute_volatility_signal,
)


def build_signal_bundle(
    raw_provider: Union[RawDataProvider, RawMarketSnapshot],
    as_of: date,
    price_symbols: List[str],
    *,
    volatility_symbols: Optional[Dict[str, str]] = None,
    liquidity_credit_symbol: Optional[str] = None,
    liquidity_credit_lqd_symbol: Optional[str] = None,
    liquidity_tip: bool = True,
    v_altitude: AltitudeRegime = "high_mid",
    c_altitude: AltitudeRegime = "high_mid",
    r_altitude: AltitudeRegime = "high_mid",
    v_recovery_params: Optional[Dict[str, dict]] = None,
) -> SignalBundle:
    """
    RawDataProvider と as_of から compute_* を呼び、SignalBundle を組み立てて返す。

    :param raw_provider: Layer 1 の取得窓口（例: CachedRawDataProvider）、または RawMarketSnapshot。
    :param as_of: 清算値の「当日」バー検索に使う基準日。
    :param price_symbols: P/T 用銘柄リスト（例: ["NQ", "GC"]）。
    :param volatility_symbols: 銘柄→ボラ指数シンボル。None なら NQ→VXN, 他→GVZ。
    :param liquidity_credit_symbol: C因子用（例: "HYG"）。None なら取得しない。
    :param liquidity_tip: R因子用 TIP を使うか。
    :param v_recovery_params: 銘柄→V因子の高度スライス（V1_off, V2_off 等）。
    """
    vol_map = volatility_symbols or {
        s: "VXN" if s == "NQ" else "GVZ" for s in price_symbols
    }

    provider: RawDataProvider = (
        cached_raw_data_provider_from_snapshot(raw_provider)
        if isinstance(raw_provider, RawMarketSnapshot)
        else raw_provider
    )

    price_signals: Dict[str, PriceSignals] = {
        sym: compute_price_signals(provider, sym, as_of)
        for sym in price_symbols
    }

    vol_signals: Dict[str, VolatilitySignal] = {}
    for sym in price_symbols:
        th = v_recovery_params.get(sym) if v_recovery_params else None
        v1_off = float(th["V1_off"]) if th and "V1_off" in th else None
        v2_off = float(th["V2_off"]) if th and "V2_off" in th else None
        vol_signals[sym] = compute_volatility_signal(
            provider,
            sym,
            as_of,
            v_altitude,
            v1_off_threshold=v1_off,
            v2_off_threshold=v2_off,
        )

    cap_signals = compute_capital_signals(provider, as_of)

    liquidity_credit: Optional[LiquiditySignals] = None
    liquidity_credit_lqd: Optional[LiquiditySignals] = None
    if liquidity_credit_symbol:
        liquidity_credit = compute_liquidity_signals_credit(
            provider, liquidity_credit_symbol, as_of, c_altitude
        )
        if liquidity_credit_lqd_symbol:
            liquidity_credit_lqd = compute_liquidity_signals_credit(
                provider, liquidity_credit_lqd_symbol, as_of, c_altitude
            )

    liquidity_tip_sig: Optional[LiquiditySignals] = None
    if liquidity_tip:
        liquidity_tip_sig = compute_liquidity_signals_tip(
            provider, as_of, r_altitude
        )

    return SignalBundle(
        price_signals=price_signals,
        volatility_signals=vol_signals,
        liquidity_credit=liquidity_credit,
        liquidity_credit_lqd=liquidity_credit_lqd,
        liquidity_tip=liquidity_tip_sig,
        capital_signals=cap_signals,
    )
