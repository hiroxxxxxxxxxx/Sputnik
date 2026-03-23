"""
Data: Layer 1 の取得結果を NQ/GC 固定で保持するスナップショット（DTO）。

IB/DB/CSV などの取得手段に依存せず、FlightController.refresh → build_signal_bundle の入力を
「単一DTO」として扱えるようにする（案2）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional

from .raw import PriceBar, PriceBar1h, RawCapitalSnapshot, VolatilitySeriesPoint

if TYPE_CHECKING:
    from .cache import CachedRawDataProvider


@dataclass(frozen=True)
class RawMarketSnapshot:
    """
    取得済み Raw のスナップショット（NQ/GC 前提）。

    CachedRawDataProvider が内部に持つ情報と同等だが、外部API実装の詳細を隠して
    「このDTOがLayer1の正」として渡せるようにする。
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


def cached_raw_data_provider_from_snapshot(snapshot: RawMarketSnapshot) -> CachedRawDataProvider:
    """
    RawMarketSnapshot を CachedRawDataProvider に変換する（Layer2 compute の既存実装を再利用するため）。

    import は関数内に閉じ、data モジュール間の循環 import を避ける。
    """
    from .cache import CachedRawDataProvider

    cache = CachedRawDataProvider()
    cache._price_bars["NQ"] = list(snapshot.nq_price_bars)
    cache._price_bars["GC"] = list(snapshot.gc_price_bars)
    cache._price_bars_1h["NQ"] = list(snapshot.nq_price_bars_1h)
    cache._price_bars_1h["GC"] = list(snapshot.gc_price_bars_1h)
    cache._volatility_series["NQ"] = list(snapshot.nq_volatility_series)
    cache._volatility_series["GC"] = list(snapshot.gc_volatility_series)
    cache._capital_snapshot = snapshot.capital_snapshot
    cache._credit_bars = {k: list(v) for k, v in snapshot.credit_bars.items()}
    cache._tip_bars = list(snapshot.tip_bars)
    return cache
