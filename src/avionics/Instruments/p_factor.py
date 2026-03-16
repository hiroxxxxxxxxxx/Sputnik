"""
P因子（Price Stress）：価格ストレス計器。

銘柄に依存せず、注入されたしきい値マトリクスに従って P0/P1/P2 を判定する。
しきい値は設定ファイル（config/factors.toml）で定義し、起動時に DI する。
入力は Layer 2 の出力（シグナル）のみ。Raw Data を直接参照しない。
定義書「4-2-1-1 P因子（Price Stress）」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Sequence, TYPE_CHECKING

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import PriceDailyRow, PriceSignals, SignalBundle


TrendType = Literal["up", "down", "flat"]


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

    async def update(self) -> None:
        """
        最新の価格データから P レベルを更新する。

        実データは上位で注入する想定。未注入時は安全なデフォルトで update_from_signals を呼ぶ。
        定義書「3-1 PFD」「4-2-1-1 P因子」参照。
        """
        await self.update_from_signals(
            daily_change=0.0,
            cum5_change=0.0,
            downside_gap=-0.01,
            trend="up",
            recovery_confirm_satisfied_days=0,
            cum2_change=None,
        )

    async def update_from_signal_bundle(
        self, symbol: Optional[str], bundle: "SignalBundle"
    ) -> None:
        price = getattr(bundle, "price_signals", {}).get(symbol) if symbol else None
        if price is not None:
            await self.update_from_price_signals(price)
        else:
            await self.update()

    def _count_recovery_satisfied_days(
        self,
        daily_history: Sequence[tuple],
    ) -> int:
        """基準日から遡り、P0 条件を満たす連続日数を返す。daily_history は newest first。"""
        count = 0
        for row in daily_history:
            if len(row) < 6:
                break
            _date, daily_change, cum5_change, downside_gap, trend, cum2_change = (
                row[0], row[1], row[2], row[3], row[4], row[5] if len(row) > 5 else None
            )
            if self._classify(
                daily_change=daily_change,
                cum5_change=cum5_change,
                downside_gap=downside_gap,
                trend=trend,
                cum2_change=cum2_change,
            ) == 0:
                count += 1
            else:
                break
        return count

    def get_recovery_progress_from_bundle(self, symbol: str, bundle: Any) -> Optional[tuple[int, int]]:
        """bundle の price_signals[symbol].daily_history から復帰 x/N を算出。"""
        price = getattr(bundle, "price_signals", {}).get(symbol)
        daily_history = getattr(price, "daily_history", ()) if price else ()
        count = self._count_recovery_satisfied_days(daily_history) if daily_history else 0
        confirm = int(self.thresholds["confirm_days"])
        return (min(count, confirm), confirm)

    async def update_from_price_signals(self, signals: PriceSignals) -> LevelType:
        """
        Layer 2 の PriceSignals から P レベルを更新する。

        因子は Layer 2 の出力のみを入力とする（定義書 4-2）。
        復帰連続日数は daily_history を基準日から遡って数える（ステートレス）。
        """
        daily_history = getattr(signals, "daily_history", ())
        recovery_satisfied = (
            self._count_recovery_satisfied_days(daily_history) if daily_history else 0
        )
        return await self.update_from_signals(
            daily_change=signals.daily_change,
            cum5_change=signals.cum5_change,
            downside_gap=signals.downside_gap,
            trend=signals.trend,
            cum2_change=signals.cum2_change,
            recovery_confirm_satisfied_days=recovery_satisfied,
        )

    async def update_from_signals(
        self,
        daily_change: float,
        cum5_change: float,
        downside_gap: float,
        trend: TrendType,
        recovery_confirm_satisfied_days: int,
        cum2_change: Optional[float] = None,
    ) -> LevelType:
        """
        事前計算済みシグナル（Layer 2 出力）から P レベルを更新する。

        しきい値はコンストラクタで注入されたもののみを使用。銘柄分岐なし。
        悪化は即時、改善は confirm_days 連続確認（計器のノイズ除去）。
        定義書「0-4」「4-2-1-1」「4-2 情報の階層構造」参照。
        """
        new_level = self._classify(
            daily_change=daily_change,
            cum5_change=cum5_change,
            downside_gap=downside_gap,
            trend=trend,
            cum2_change=cum2_change,
        )

        if new_level > self.level:
            self.downgrade(new_level)
        elif new_level < self.level:
            confirm = int(self.thresholds["confirm_days"])
            await self.upgrade(
                new_level,
                confirm_days=confirm,
                recovery_confirm_satisfied_days=recovery_confirm_satisfied_days,
            )
        else:
            self.record_level()

        return self.level

    def _classify(
        self,
        daily_change: float,
        cum5_change: float,
        downside_gap: float,
        trend: TrendType,
        cum2_change: Optional[float] = None,
    ) -> LevelType:
        """
        注入されたしきい値のみで P レベルを判定する純粋関数。銘柄は参照しない。
        定義書「4-2-1-1 P因子」参照。
        """
        t = self.thresholds
        # P2: ショック条件
        if daily_change <= t["P2_daily_max"]:
            return 2
        if cum2_change is not None and cum2_change <= t["P2_cum2_max"]:
            return 2
        if downside_gap < t["P2_gap_trend"] and trend == "down":
            return 2

        # P1: プレッシャー条件
        if t["P1_daily_lo"] < daily_change <= t["P1_daily_hi"]:
            return 1
        if t["P1_cum5_lo"] <= cum5_change < t["P1_cum5_hi"]:
            return 1
        if t["P1_gap_lo"] <= downside_gap <= t["P1_gap_hi"]:
            return 1

        # P0: Calm（すべて満たす）
        if (
            abs(daily_change) <= t["P0_daily_abs"]
            and cum5_change >= t["P0_cum5_min"]
            and downside_gap > t["P0_gap_min"]
            and trend == "up"
        ):
            return 0

        return 1
