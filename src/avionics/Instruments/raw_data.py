"""
Layer 1（Raw Data）：未加工データの型と取得インターフェース。

終値・出来高・IV・証拠金・VIX 等の未加工データを保持または取得する責務を定義する。
加工（変動率・トレンド・SMA・比率など）は行わない。実装は DB/API/CSV 等に委譲。
定義書「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Protocol, Tuple

# 復帰確認用。直近 N 営業日分の (日付, 指数値)。日付昇順を想定。
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
    陽線判定は close > open で行う。
    """
    bar_end: datetime  # バー確定時刻（現物クローズに合わせる場合は ET）
    open: float
    close: float
    high: float
    volume: float


@dataclass(frozen=True)
class RawCapitalSnapshot:
    """
    証拠金・NLV 等の内部 Raw。U/S 用シグナル計算の元。

    S 因子用: current_density = mm / (current_value * futures_multiplier),
    span_ratio = current_density / base_density は Layer 2 で算出。
    定義書「4-2-3 LCL」「4-2-3-1 U因子」「4-2-3-2 S因子」参照。
    """
    as_of: date
    mm: float
    nlv: float
    base_density: float
    current_value: float = 0.0
    futures_multiplier: float = 1.0


class RawDataProvider(Protocol):
    """
    Layer 1 の取得窓口。実装は DB/API/CSV 等で差し替え可能。

    定義書「4-2 情報の階層構造」参照。
    """

    def get_price_series(self, symbol: str, limit: int) -> List[PriceBar]:
        """銘柄の日足価格系列（直近 limit 本）。終値はNY現物クローズ（ET 16:00）基準。"""
        ...

    def get_price_series_1h(self, symbol: str, limit: int) -> List[PriceBar1h]:
        """銘柄の1h足系列（直近 limit 本）。NY現物時間（ET 09:30〜16:00）に合わせる。未実装なら []。"""
        ...

    def get_volatility_index(self, symbol: str, as_of: date) -> Optional[float]:
        """VXN/GVZ 相当のボラティリティ指数を取得する。"""
        ...

    def get_volatility_series(self, symbol: str, limit: int) -> List[VolatilitySeriesPoint]:
        """直近 limit 営業日分の (日付, 指数値)。復帰確認の連続日数算出用。未実装なら []。"""
        ...

    def get_capital_snapshot(self, as_of: date) -> Optional[RawCapitalSnapshot]:
        """証拠金・NLV・SPAN 用 Raw を取得する。"""
        ...

    def get_credit_series(self, symbol: str, limit: int) -> List[PriceBar]:
        """HYG/LQD 等のクレジット ETF 価格系列。L 因子 credit 用。"""
        ...

    def get_tip_series(self, limit: int) -> List[PriceBar]:
        """TIP 価格系列（高値含む）。L 因子 tip 用。"""
        ...
