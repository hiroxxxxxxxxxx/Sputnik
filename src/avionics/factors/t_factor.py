"""
T因子（Trend）：銘柄固有のトレンド判定。サブスクリプション方式に準拠。

担当銘柄のトレンド（up/down/flat）は Layer 2 の Signal であり、T はその Signal を
入力に T0/T2 を出力する。出力 level は同期制御層（T 相関）の入力として扱う。
Raw Data を直接参照しない。NQ/GC をセットで見る「一括監視」は廃止。
定義書「4-2-1-4 T因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle


TrendType = Literal["up", "down", "flat"]


class TFactor(BaseFactor):
    """
    T因子（Trend）：銘柄固有のトレンド判定。

    担当銘柄のトレンドだけを監視する。down → T2（即時）、up/flat → T0（復帰は継続確認）。
    非対称ヒステリシス厳守。定義書「4-2-1-4」「0-4」参照。
    """

    def __init__(self, symbol: str, thresholds: dict, history_size: int = 64) -> None:
        """
        T因子を初期化する。

        :param symbol: 担当銘柄（"NQ" / "GC" 等）。サブスクリプションでこの銘柄の M にのみ寄与する。
        :param thresholds: しきい値辞書（confirm_days）。config/factors.toml の [T] から注入。
        :param history_size: レベル履歴バッファ長
        定義書「4-2-1-4 T因子」参照。
        """
        self.symbol: str = symbol
        self._thresholds: dict = dict(thresholds)
        super().__init__(
            name=f"T_{symbol}",
            levels=[0, 2],
            history_size=history_size,
        )

    def _count_recovery_satisfied_days(
        self,
        daily_history: tuple,
    ) -> int:
        """基準日から遡り、trend が up/flat の連続日数を返す。daily_history は newest first。(date, dc, c5, gap, trend, c2)。"""
        count = 0
        for row in daily_history:
            if len(row) >= 5 and row[4] in ("up", "flat"):
                count += 1
            else:
                break
        return count

    def get_recovery_progress_from_bundle(self, symbol: str, bundle: Any) -> Optional[tuple[int, int]]:
        """bundle の price_signals[symbol].daily_history から復帰 x/N を算出。"""
        price = getattr(bundle, "price_signals", {}).get(symbol)
        daily_history = getattr(price, "daily_history", ()) if price else ()
        count = self._count_recovery_satisfied_days(daily_history) if daily_history else 0
        confirm = int(self._thresholds["confirm_days"])
        return (min(count, confirm), confirm)

    async def apply_signal_bundle(
        self, symbol: Optional[str], bundle: "SignalBundle"
    ) -> None:
        price = getattr(bundle, "price_signals", {}).get(symbol) if symbol else None
        if price is not None:
            await self.apply_trend(
                price.trend,
                daily_history=getattr(price, "daily_history", ()),
            )

    async def apply_trend(
        self,
        trend: TrendType,
        daily_history: tuple = (),
    ) -> LevelType:
        """
        銘柄別トレンド Signal（Layer 2）を反映し、ヒステリシスを伴ってレベルを更新する。

        :param trend: 担当銘柄のトレンド Signal（"up" / "down" / "flat"）
        :param daily_history: 基準日から遡った日次値（newest first）。復帰連続日数算出用。
        :return: 更新後のレベル（0 または 2）

        down → T2 は即時降格。T2 → T0 は閾値 confirm_days の期間連続 up/flat 確認後に昇格（ステートレス）。
        定義書「0-4」「4-2-1-4」参照。
        """
        new_level: LevelType = 2 if trend == "down" else 0
        confirm_days = int(self._thresholds["confirm_days"])
        recovery_satisfied = (
            self._count_recovery_satisfied_days(daily_history) if daily_history else 0
        )

        if new_level > self.level:
            self.downgrade(new_level)
        elif new_level < self.level:
            await self.upgrade(
                new_level,
                confirm_days=confirm_days,
                recovery_confirm_satisfied_days=recovery_satisfied,
            )
        else:
            self.record_level()

        return self.level
