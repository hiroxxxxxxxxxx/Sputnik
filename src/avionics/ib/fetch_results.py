from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..data.account_positions import PositionDetailBySymbol, PositionLegsBySymbol
from ..data.raw_types import PriceBar, PriceBar1h, RawCapitalSnapshot, VolatilitySeriesPoint


@dataclass(frozen=True)
class MarketFetchResult:
    """マーケット系取得結果（Layer1）。"""

    price_bars: Dict[str, List[PriceBar]] = field(default_factory=dict)
    volatility_series: Dict[str, List[VolatilitySeriesPoint]] = field(default_factory=dict)
    credit_bars: Dict[str, List[PriceBar]] = field(default_factory=dict)
    tip_bars: List[PriceBar] = field(default_factory=list)
    bars_1h: Dict[str, List[PriceBar1h]] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountFetchResult:
    """口座系取得結果（Layer1）。"""

    capital: Optional[RawCapitalSnapshot]
    positions_legs: PositionLegsBySymbol
    positions_detail: PositionDetailBySymbol
