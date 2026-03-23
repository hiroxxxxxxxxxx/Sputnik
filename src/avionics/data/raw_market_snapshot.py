"""
Data: Layer 1 の取得結果を NQ/GC 固定で保持するスナップショット（DTO）。

IB/DB/CSV などの取得手段に依存せず、FlightController.refresh → build_signal_bundle の入力を
「単一DTO」として扱えるようにする（案2）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .raw import PriceBar, PriceBar1h, RawCapitalSnapshot, VolatilitySeriesPoint


@dataclass(frozen=True)
class RawMarketSnapshot:
    """
    取得済み Raw のスナップショット（NQ/GC 前提）。

    取得済み系列（NQ/GC の価格/ボラ/流動性/資本など）を保持する。
    外部API実装の詳細を隠し、「このDTOがLayer1の正」として渡せるようにする。
    """

    as_of: date

    nq_price_bars: List[PriceBar] = field(default_factory=list)
    gc_price_bars: List[PriceBar] = field(default_factory=list)

    nq_price_bars_1h: List[PriceBar1h] = field(default_factory=list)
    gc_price_bars_1h: List[PriceBar1h] = field(default_factory=list)

    nq_volatility_series: List[VolatilitySeriesPoint] = field(default_factory=list)
    gc_volatility_series: List[VolatilitySeriesPoint] = field(default_factory=list)

    capital_snapshot: Optional[RawCapitalSnapshot] = None

    credit_bars: Dict[str, List[PriceBar]] = field(default_factory=dict)
    tip_bars: List[PriceBar] = field(default_factory=list)
