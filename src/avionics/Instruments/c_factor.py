"""
C因子（Credit Stress）：NQ系専用。信用収縮の検知。

HYG/LQD の below_sma20 または前日比で C0/C2 を判定する。C1廃止。二択のみ。
悪化は即時、復帰は confirm_days 連続確認。
定義書「4-2-1-3 C因子（Credit Stress：NQ系）」参照。
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from .signals import LiquiditySignals


class CFactor(BaseFactor):
    """
    C因子（Credit Stress）：NQ系専用。

    C2発動（即）: SMA20を下回る OR 前日比が閾値以下。
    C0復帰（2日確認）: SMA20以上を維持。
    定義書「4-2-1-3」「0-4」参照。
    """

    def __init__(
        self,
        name: str,
        thresholds: dict,
        history_size: int = 64,
    ) -> None:
        """
        C因子を初期化する。

        :param name: 表示用ラベル（例: "C"）。
        :param thresholds: しきい値辞書（daily_change_C2, confirm_days）。factors_config.get_c_thresholds で注入。
        :param history_size: レベル履歴バッファ長
        定義書「4-2-1-3 C因子」参照。
        """
        self.thresholds: dict = dict(thresholds)
        super().__init__(name=name, levels=[0, 2], history_size=history_size)

    async def update(self) -> None:
        """
        未注入時は安全なデフォルトで update_from_signals を呼ぶ。
        定義書「3-1 PFD」「4-2-1-3 C因子」参照。
        """
        await self.update_from_signals(
            altitude="high_mid",
            below_sma20=False,
            daily_change=0.0,
        )

    def _count_recovery_satisfied_days(
        self,
        daily_history_credit: tuple,
    ) -> int:
        """基準日から遡り、C0 条件（not below_sma20 and daily_change > C2）を満たす連続日数を返す。(date, below_sma20, daily_change)。"""
        th = self.thresholds
        c2_th = float(th["daily_change_C2"])
        count = 0
        for row in daily_history_credit:
            if len(row) >= 3 and not row[1] and row[2] > c2_th:
                count += 1
            else:
                break
        return count

    def get_recovery_progress_from_bundle(self, symbol: str, bundle: Any) -> Optional[tuple[int, int]]:
        """bundle の liquidity_credit から復帰 x/N を算出。"""
        credit = getattr(bundle, "liquidity_credit", None)
        if not credit:
            return None
        daily_history_credit = getattr(credit, "daily_history_credit", ()) or ()
        count = self._count_recovery_satisfied_days(daily_history_credit) if daily_history_credit else 0
        confirm = int(self.thresholds["confirm_days"])
        return (min(count, confirm), confirm)

    async def update_from_signals(
        self,
        altitude: str,
        below_sma20: bool,
        daily_change: float,
        daily_history_credit: tuple = (),
    ) -> LevelType:
        """
        事前計算済みシグナル（LiquiditySignals 相当）から C レベルを更新する。

        C2発動（即）: below_sma20 または daily_change <= daily_change_C2。
        C0復帰: 上記を満たさない日が confirm_days 連続（ステートレス）。
        定義書「0-4」「4-2-1-3」参照。
        """
        th = self.thresholds
        daily_change_C2 = float(th["daily_change_C2"])
        confirm_days = int(th["confirm_days"])

        c2_triggered = below_sma20 or (daily_change <= daily_change_C2)
        c0_condition_met = not c2_triggered
        recovery_satisfied = (
            self._count_recovery_satisfied_days(daily_history_credit)
            if daily_history_credit
            else 0
        )

        if c2_triggered:
            self.downgrade(2)
            return 2

        if self.level == 2:
            await self.upgrade(
                0,
                confirm_days,
                recovery_confirm_satisfied_days=recovery_satisfied,
                condition_met=c0_condition_met,
            )
        return self.level
