"""
P因子（Price Stress）：価格ストレス計器。

銘柄に依存せず、注入されたしきい値マトリクスに従って P0/P1/P2 を判定する。
しきい値は設定ファイル（config/factors.toml）で定義し、起動時に DI する。
入力は Layer 2 の出力（シグナル）のみ。Raw Data を直接参照しない。
定義書「4-2-1-1 P因子（Price Stress）」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional, TYPE_CHECKING

from avionics.data.signals import PriceDailyRow
from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import AltitudeRegime, PriceSignals, SignalBundle


TrendType = Literal["up", "down", "flat"]

PClassifyReasonId = Literal[
    "P2_daily",
    "P2_cum2",
    "P2_gap_down",
    "P1_daily_band",
    "P1_cum5_band",
    "P1_gap_band",
    "P0_relaxed",
    "P1_default",
]

_P_HIT_KEYS: dict[PClassifyReasonId, frozenset[str]] = {
    "P2_daily": frozenset({"daily_change"}),
    "P2_cum2": frozenset({"cum2_change"}),
    "P2_gap_down": frozenset({"high_20_gap", "trend"}),
    "P1_daily_band": frozenset({"daily_change"}),
    "P1_cum5_band": frozenset({"cum5_change"}),
    "P1_gap_band": frozenset({"high_20_gap"}),
    "P0_relaxed": frozenset({"daily_change", "cum5_change", "high_20_gap", "trend"}),
    "P1_default": frozenset(),
}


def p_classify_row_hit_row_keys(reason: PClassifyReasonId) -> frozenset[str]:
    """breakdown 行キー（日次・累積・乖離・トレンド）のどれに ★ を付けるか。"""
    return _P_HIT_KEYS[reason]


def p_classify_row_with_reason(
    thresholds: dict,
    daily_change: float,
    cum5_change: float,
    high_20_gap: float,
    trend: TrendType,
    cum2_change: Optional[float],
) -> tuple[LevelType, PClassifyReasonId]:
    t = thresholds
    if daily_change <= t["P2_daily_max"]:
        return 2, "P2_daily"
    if cum2_change is not None and cum2_change <= t["P2_cum2_max"]:
        return 2, "P2_cum2"
    if high_20_gap < t["P2_gap_trend"] and trend == "down":
        return 2, "P2_gap_down"
    if t["P1_daily_lo"] < daily_change <= t["P1_daily_hi"]:
        return 1, "P1_daily_band"
    if t["P1_cum5_lo"] <= cum5_change < t["P1_cum5_hi"]:
        return 1, "P1_cum5_band"
    if t["P1_gap_lo"] <= high_20_gap <= t["P1_gap_hi"]:
        return 1, "P1_gap_band"
    if (
        abs(daily_change) <= t["P0_daily_abs"]
        and cum5_change >= t["P0_cum5_min"]
        and high_20_gap > t["P0_gap_min"]
        and trend == "up"
    ):
        return 0, "P0_relaxed"
    return 1, "P1_default"


def p_level_from_daily_rows(
    rows_oldest_first: list[PriceDailyRow],
    thresholds: dict,
) -> LevelType:
    """最新 1 行（rows_oldest_first の末尾）だけで P レベルを決定する（インスタンス状態に依存しない）。"""
    if not rows_oldest_first:
        raise ValueError("p_level_from_daily_rows requires at least one PriceDailyRow")
    row = rows_oldest_first[-1]
    if len(row) < 6:
        raise ValueError(
            "p_level_from_daily_rows requires the latest row to have at least 6 fields "
            "(date, daily_change, cum5_change, high_20_gap, trend, cum2_change)"
        )
    _dt, daily_change, cum5_change, high_20_gap, trend, cum2_change = (
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        row[5] if len(row) > 5 else None,
    )
    return _p_classify_row(
        thresholds,
        daily_change,
        cum5_change,
        high_20_gap,
        trend,
        cum2_change,
    )


def _p_classify_row(
    thresholds: dict,
    daily_change: float,
    cum5_change: float,
    high_20_gap: float,
    trend: TrendType,
    cum2_change: Optional[float],
) -> LevelType:
    return p_classify_row_with_reason(
        thresholds,
        daily_change,
        cum5_change,
        high_20_gap,
        trend,
        cum2_change,
    )[0]


class PFactor(BaseFactor):
    """
    P因子（Price Stress）：価格ストレス計器。

    銘柄名は持たず、注入されたしきい値のみで判定する「計算機」に徹する。
    レベルは最新営業日相当のシグナル行から決まる（履歴の畳み込みや N 日確認は用いない）。
    定義書「4-2-1-1」参照。
    """

    def __init__(
        self,
        name: str,
        thresholds: dict,
        history_size: int = 64,
    ) -> None:
        """
        P因子を初期化する。

        :param name: 表示用ラベル（例: "P_NQ"）。銘柄の「意味」は持たない。
        :param thresholds: しきい値辞書（P2_*, P1_*, P0_*）。設定ファイルから注入。
        :param history_size: レベル履歴バッファ長
        定義書「3-1 PFD」「4-2-1-1 P因子」参照。
        """
        self.thresholds: dict = dict(thresholds)
        super().__init__(name=name, levels=[0, 1, 2], history_size=history_size)

    async def apply_signal_bundle(
        self,
        symbol: Optional[str],
        bundle: "SignalBundle",
        *,
        altitude: "AltitudeRegime",
    ) -> None:
        price = getattr(bundle, "price_signals", {}).get(symbol) if symbol else None
        if price is not None:
            await self.update_from_price_signals(price)

    def _price_rows_oldest_first(self, signals: "PriceSignals") -> list[PriceDailyRow]:
        """daily_history（newest first）を古い順に並べ替え。空なら当日スナップショット 1 行のみ。"""
        if signals.high_20_gap is None:
            raise ValueError("PriceSignals.high_20_gap is required for PFactor")
        dh = list(signals.daily_history)
        if dh:
            return list(reversed(dh))
        return [
            (
                date.min,
                signals.daily_change,
                signals.cum5_change,
                signals.high_20_gap,
                signals.trend,
                signals.cum2_change,
            )
        ]

    def latest_price_daily_row(self, signals: "PriceSignals") -> PriceDailyRow:
        """最新営業日相当の 1 行。breakdown の P 分類・★ 表示用。"""
        rows = self._price_rows_oldest_first(signals)
        return rows[-1]

    async def update_from_price_signals(self, signals: "PriceSignals") -> LevelType:
        """
        Layer 2 の PriceSignals から P レベルを更新する。

        因子は Layer 2 の出力のみを入力とする（定義書 4-2）。
        最新行のみで分類し、インスタンスの前回 level に依存しない。
        """
        rows = self._price_rows_oldest_first(signals)
        level = p_level_from_daily_rows(rows, self.thresholds)
        self.assign_level_from_computation(level)
        return level

    async def update_from_signals(
        self,
        daily_change: float,
        cum5_change: float,
        high_20_gap: float,
        trend: TrendType,
        recovery_confirm_satisfied_days: int,
        cum2_change: Optional[float] = None,
    ) -> LevelType:
        """
        事前計算済みシグナル（Layer 2 出力）から P レベルを更新する（テスト・直接呼び出し用）。

        recovery_confirm_satisfied_days は互換のため受け取るが無視される。
        """
        _ = recovery_confirm_satisfied_days
        row: PriceDailyRow = (
            date.min,
            daily_change,
            cum5_change,
            high_20_gap,
            trend,
            cum2_change,
        )
        level = p_level_from_daily_rows([row], self.thresholds)
        self.assign_level_from_computation(level)
        return level

    def _classify(
        self,
        daily_change: float,
        cum5_change: float,
        high_20_gap: float,
        trend: TrendType,
        cum2_change: Optional[float] = None,
    ) -> LevelType:
        """互換: 純関数分類。"""
        return _p_classify_row(
            self.thresholds,
            daily_change,
            cum5_change,
            high_20_gap,
            trend,
            cum2_change,
        )
