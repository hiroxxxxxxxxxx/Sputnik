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
    "P0_calm",
    "P1_default",
]


def _p0_axis_pass(
    thresholds: dict,
    daily_change: float,
    cum5_change: float,
    high_20_gap: float,
    trend: TrendType,
) -> tuple[bool, bool, bool, bool]:
    """P0（Calm）の各軸が成立するか。判定式はここだけが正。"""
    t = thresholds
    return (
        daily_change >= -t["P0_daily_abs"],
        cum5_change >= t["P0_cum5_min"],
        high_20_gap > t["P0_gap_min"],
        trend == "up",
    )


def p_failed_p0_row_keys(
    thresholds: dict,
    daily_change: float,
    cum5_change: float,
    high_20_gap: float,
    trend: TrendType,
) -> frozenset[str]:
    """P0 条件のうち不成立になった入力行キーだけを返す。"""
    ok_daily, ok_c5, ok_gap, ok_trend = _p0_axis_pass(thresholds, daily_change, cum5_change, high_20_gap, trend)
    keys: set[str] = set()
    if not ok_daily:
        keys.add("daily_change")
    if not ok_c5:
        keys.add("cum5_change")
    if not ok_gap:
        keys.add("high_20_gap")
    if not ok_trend:
        keys.add("trend")
    return frozenset(keys)


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
    if all(_p0_axis_pass(t, daily_change, cum5_change, high_20_gap, trend)):
        return 0, "P0_calm"
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


def _p_row_tuple_for_classify(row: PriceDailyRow) -> tuple[float, float, float, TrendType, Optional[float]]:
    _dt, daily_change, cum5_change, high_20_gap, trend, cum2_change = (
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        row[5] if len(row) > 5 else None,
    )
    return daily_change, cum5_change, high_20_gap, trend, cum2_change


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
        self.last_classify_reason: PClassifyReasonId | None = None
        self.last_p0_failed_row_keys: frozenset[str] | None = None
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
        """最新営業日相当の 1 行（daily_history があれば newest-first 先頭、なければ当日スナップショット 1 行）。

        Layer 2 の compute が先頭行とトップレベルを揃えるため、breakdown の表・★ と一致する。
        """
        rows = self._price_rows_oldest_first(signals)
        return rows[-1]

    def _apply_classify_row_and_cache(self, row: PriceDailyRow) -> LevelType:
        dc, c5, hg, tr, c2 = _p_row_tuple_for_classify(row)
        level, rid = p_classify_row_with_reason(self.thresholds, dc, c5, hg, tr, c2)
        self.last_classify_reason = rid
        self.last_p0_failed_row_keys = p_failed_p0_row_keys(self.thresholds, dc, c5, hg, tr)
        return level

    async def update_from_price_signals(self, signals: "PriceSignals") -> LevelType:
        """
        Layer 2 の PriceSignals から P レベルを更新する。

        因子は Layer 2 の出力のみを入力とする（定義書 4-2）。
        最新行のみで分類し、インスタンスの前回 level に依存しない。
        """
        rows = self._price_rows_oldest_first(signals)
        level = self._apply_classify_row_and_cache(rows[-1])
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
        level = self._apply_classify_row_and_cache(row)
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
