"""
DataSource Protocol: Raw データの取得元。

FC.refresh に注入して使う。BundleBuildOptions は avionics.bundle_builder で定義。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Protocol, Tuple

from .account_positions import PositionDetailBySymbol, PositionLegsBySymbol
from .raw_types import RawCapitalSnapshot
from .raw_market_snapshot import RawMarketSnapshot


class DataSource(Protocol):
    """
    Raw を取得できるデータ源。FC.refresh に注入する。
    実装例: avionics.ib.fetcher.IBRawFetcher。
    """

    async def fetch_raw(
        self,
        as_of: date,
        price_symbols: List[str],
        *,
        volatility_symbols: Optional[Dict[str, str]] = None,
        liquidity_credit_hyg_symbol: str,
        liquidity_credit_lqd_symbol: str,
        liquidity_tip_symbol: Optional[str] = None,
        account: str = "",
        base_density: float = 1.0,
        v_recovery_params: Optional[Dict[str, dict]] = None,
    ) -> Tuple[
        RawMarketSnapshot,
        Optional[RawCapitalSnapshot],
        PositionLegsBySymbol,
        PositionDetailBySymbol,
    ]:
        ...
        """Layer 1 の Raw/口座データを取得して返す。"""
