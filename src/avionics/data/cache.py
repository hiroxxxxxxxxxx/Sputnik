"""
Data: RawDataProvider の汎用実装（メモリキャッシュ）。

取得元（IB / DB / CSV）に依存しない。Acquisition が取得した結果を詰めて RawDataProvider として渡す用。
定義書「4-2 情報の階層構造」・docs/archive/PROPOSAL_RAW_PROVIDER_LAYOUT.md 参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .raw import (
    PriceBar,
    PriceBar1h,
    RawCapitalSnapshot,
    RawDataProvider,
    VolatilitySeriesPoint,
)


@dataclass
class CachedRawDataProvider(RawDataProvider):
    """
    Layer 1 の取得窓口のキャッシュ実装。取得結果をメモリに保持し、RawDataProvider として渡す。
    IB / DB / CSV 等、どの取得手段でも詰めて利用可能。
    """

    _price_bars: Dict[str, List[PriceBar]] = field(default_factory=dict)
    _price_bars_1h: Dict[str, List[PriceBar1h]] = field(default_factory=dict)
    _volatility_series: Dict[str, List[VolatilitySeriesPoint]] = field(default_factory=dict)
    _capital_snapshot: Optional[RawCapitalSnapshot] = None
    _credit_bars: Dict[str, List[PriceBar]] = field(default_factory=dict)
    _tip_bars: List[PriceBar] = field(default_factory=list)

    def get_price_series(self, symbol: str, limit: int) -> List[PriceBar]:
        bars = self._price_bars.get(symbol, [])
        return bars[-limit:] if limit else bars

    def get_price_series_1h(self, symbol: str, limit: int) -> List[PriceBar1h]:
        bars = self._price_bars_1h.get(symbol, [])
        return bars[-limit:] if limit else bars

    def get_volatility_index(self, symbol: str, as_of: date) -> Optional[float]:
        series = self._volatility_series.get(symbol, [])
        candidates = [(d, v) for d, v in series if d <= as_of]
        return max(candidates, key=lambda x: x[0])[1] if candidates else None

    def get_volatility_series(self, symbol: str, limit: int) -> List[VolatilitySeriesPoint]:
        series = self._volatility_series.get(symbol, [])
        return series[-limit:] if limit else series

    def get_capital_snapshot(self, as_of: date) -> Optional[RawCapitalSnapshot]:
        return self._capital_snapshot

    def get_credit_series(self, symbol: str, limit: int) -> List[PriceBar]:
        bars = self._credit_bars.get(symbol, [])
        return bars[-limit:] if limit else bars

    def get_tip_series(self, limit: int) -> List[PriceBar]:
        return self._tip_bars[-limit:] if limit else self._tip_bars
