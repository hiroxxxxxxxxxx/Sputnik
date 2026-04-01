"""
P因子（Price Stress）：価格ストレス計器。

銘柄に依存せず、注入されたしきい値マトリクスに従って P0/P1/P2 を判定する。
しきい値は設定ファイル（config/factors.toml）で定義し、起動時に DI する。
入力は Layer 2 の出力（シグナル）のみ。Raw Data を直接参照しない。
定義書「4-2-1-1 P因子（Price Stress）」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional, Sequence, TYPE_CHECKING

from avionics.data.signals import PriceDailyRow
from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import AltitudeRegime, PriceSignals, SignalBundle


TrendType = Literal["up", "down", "flat"]


def p_level_from_daily_rows(
    rows_oldest_first: list[PriceDailyRow],
    thresholds: dict,
) -> LevelType:
    """daily 行（古い順）を畳み込み P レベルを決定する（インスタンス状態に依存しない）。"""
    level: LevelType = 0
    confirm = int(thresholds["confirm_days"])
    for k in range(len(rows_oldest_first)):
        row = rows_oldest_first[k]
        if len(row) < 6:
            break
        _dt, daily_change, cum5_change, high_20_gap, trend, cum2_change = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5] if len(row) > 5 else None,
        )
        newest_first_prefix = tuple(reversed(rows_oldest_first[: k + 1]))
        recovery = 0
        for r2 in newest_first_prefix:
            if len(r2) < 6:
                break
            if (
                _p_classify_row(
                    thresholds,
                    r2[1],
                    r2[2],
                    r2[3],
                    r2[4],
                    r2[5] if len(r2) > 5 else None,
                )
                == 0
            ):
                recovery += 1
            else:
                break
        new_level = _p_classify_row(
            thresholds,
            daily_change,
            cum5_change,
            high_20_gap,
            trend,
            cum2_change,
        )
        if new_level > level:
            level = new_level
        elif new_level < level:
            if recovery >= confirm:
                level = new_level
    return level


def _p_classify_row(
    thresholds: dict,
    daily_change: float,
    cum5_change: float,
    high_20_gap: float,
    trend: TrendType,
    cum2_change: Optional[float],
) -> LevelType:
    t = thresholds
    if daily_change <= t["P2_daily_max"]:
        return 2
    if cum2_change is not None and cum2_change <= t["P2_cum2_max"]:
        return 2
    if high_20_gap < t["P2_gap_trend"] and trend == "down":
        return 2
    if t["P1_daily_lo"] < daily_change <= t["P1_daily_hi"]:
        return 1
    if t["P1_cum5_lo"] <= cum5_change < t["P1_cum5_hi"]:
        return 1
    if t["P1_gap_lo"] <= high_20_gap <= t["P1_gap_hi"]:
        return 1
    if (
        abs(daily_change) <= t["P0_daily_abs"]
        and cum5_change >= t["P0_cum5_min"]
        and high_20_gap > t["P0_gap_min"]
        and trend == "up"
    ):
        return 0
    return 1


class PFactor(BaseFactor):
    """
    P因子（Price Stress）：価格ストレス計器。

    銘柄名は持たず、注入されたしきい値のみで判定する「計算機」に徹する。
    悪化は即時、改善は confirm_days 連続確認（ノイズ除去用・1日推奨）。
    定義書「4-2-1-1」「0-4」参照。
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
        :param thresholds: しきい値辞書（P2_*, P1_*, P0_*, confirm_days）。設定ファイルから注入。
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

    def _count_recovery_satisfied_days(
        self,
        daily_history: Sequence[tuple],
    ) -> int:
        """基準日から遡り、P0 条件を満たす連続日数を返す。daily_history は newest first。"""
        count = 0
        for row in daily_history:
            if len(row) < 6:
                break
            _date, daily_change, cum5_change, high_20_gap, trend, cum2_change = (
                row[0], row[1], row[2], row[3], row[4], row[5] if len(row) > 5 else None
            )
            if self._classify(
                daily_change=daily_change,
                cum5_change=cum5_change,
                high_20_gap=high_20_gap,
                trend=trend,
                cum2_change=cum2_change,
            ) == 0:
                count += 1
            else:
                break
        return count

    def get_recovery_progress_from_bundle(
        self,
        symbol: str,
        bundle: Any,
        *,
        altitude: "AltitudeRegime",
    ) -> Optional[tuple[int, int]]:
        """bundle の price_signals[symbol].daily_history から復帰 x/N を算出。"""
        price = getattr(bundle, "price_signals", {}).get(symbol)
        daily_history = getattr(price, "daily_history", ()) if price else ()
        count = self._count_recovery_satisfied_days(daily_history) if daily_history else 0
        confirm = int(self.thresholds["confirm_days"])
        return (min(count, confirm), confirm)

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

    async def update_from_price_signals(self, signals: "PriceSignals") -> LevelType:
        """
        Layer 2 の PriceSignals から P レベルを更新する。

        因子は Layer 2 の出力のみを入力とする（定義書 4-2）。
        日次履歴を畳み込み、インスタンスの前回 level に依存しない。
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

        recovery_confirm_satisfied_days は無視され、単一日行のみ畳み込む。
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
