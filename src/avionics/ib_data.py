"""
IB（Interactive Brokers）API 経由で FlightController 用 Layer 1 データを取得し、SignalBundle を組み立てる。

案B B-2: Acquisition（ib_fetcher）と Process（bundle_builder）に分割済み。
このモジュールは互換用の窓口。IBDataFetcher は fetch_raw + build_signal_bundle を組み合わせて fetch_signal_bundle を提供する。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from .acquisition.ib_fetcher import IBDataFetcher as _IBDataFetcher
from .data.cache import CachedRawDataProvider
from .data.raw import RawCapitalSnapshot
from .data.signals import AltitudeRegime, SignalBundle
from .process.layer2.bundle_builder import build_signal_bundle


class IBDataFetcher(_IBDataFetcher):
    """
    ib_async の IB インスタンスを使い、FlightController 用 SignalBundle を非同期で取得する。

    内部で acquisition の fetch_raw と process.layer2 の build_signal_bundle を組み合わせている。
    定義書「4-2 情報の階層構造」参照。
    """

    async def fetch_signal_bundle(
        self,
        as_of: date,
        price_symbols: List[str],
        volatility_symbols: Optional[Dict[str, str]] = None,
        liquidity_credit_symbol: Optional[str] = None,
        liquidity_tip: bool = True,
        base_density: float = 1.0,
        v_altitude: AltitudeRegime = "high_mid",
        c_altitude: AltitudeRegime = "high_mid",
        r_altitude: AltitudeRegime = "high_mid",
        account: str = "",
        v_recovery_params: Optional[Dict[str, dict]] = None,
    ) -> Tuple[SignalBundle, Optional[RawCapitalSnapshot]]:
        """
        IB から Raw を取得し、Layer 2 計算で SignalBundle を組み立てる。

        :param as_of: 取得・算出の基準日。清算値の「当日」バー検索にも使う。
        :param liquidity_credit_symbol: C因子用（例: "HYG"）。None のときは取得しない。
        :param liquidity_tip: R因子用 TIP 系列を取得するか。
        :param v_recovery_params: 銘柄→V因子の高度スライス（V1_off, V2_off 等）。
        :return: (SignalBundle, RawCapitalSnapshot または None)。
        """
        cache, capital_snapshot = await self.fetch_raw(
            as_of,
            price_symbols,
            volatility_symbols=volatility_symbols,
            liquidity_credit_symbol=liquidity_credit_symbol,
            liquidity_tip=liquidity_tip,
            account=account,
            base_density=base_density,
            v_recovery_params=v_recovery_params,
        )
        lqd_symbol: Optional[str] = None
        if (liquidity_credit_symbol or "").upper() == "HYG" and "LQD" in cache._credit_bars:
            lqd_symbol = "LQD"
        bundle = build_signal_bundle(
            cache,
            as_of,
            price_symbols,
            volatility_symbols=volatility_symbols,
            liquidity_credit_symbol=liquidity_credit_symbol,
            liquidity_credit_lqd_symbol=lqd_symbol,
            liquidity_tip=liquidity_tip,
            v_altitude=v_altitude,
            c_altitude=c_altitude,
            r_altitude=r_altitude,
            v_recovery_params=v_recovery_params,
        )
        return bundle, capital_snapshot
