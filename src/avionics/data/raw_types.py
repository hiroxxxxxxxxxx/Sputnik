"""
Data: Layer 1 の型定義。

未加工データの形のみ定義。加工・計算は行わない。
定義書「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Tuple

VolatilitySeriesPoint = Tuple[date, float]


@dataclass(frozen=True)
class PriceBar:
    """
    1本の価格（終値・高値・出来高など）。Layer 1 の最小単位。
    定義書「4-2 Layer 1 Raw Data」参照。
    """
    date: date
    close: float
    high: float
    volume: float


@dataclass(frozen=True)
class PriceBar1h:
    """
    1本の1h足価格。NY現物時間（ET 09:30〜16:00）に合わせて取得する用。
    SPEC 4-2-1-2（1hノックイン）・Layer2「1h足陽線判定」参照。
    """
    bar_end: datetime
    open: float
    close: float
    high: float
    volume: float


@dataclass(frozen=True)
class RawCapitalSnapshot:
    """
    証拠金・NLV 等の内部 Raw。U/S 用シグナル計算の元。
    定義書「4-2-3 LCL」「4-2-3-1 U因子」「4-2-3-2 S因子」参照。
    """
    as_of: date
    mm: float
    nlv: float
    base_density: float
    current_value: float = 0.0
    futures_multiplier: float = 1.0
