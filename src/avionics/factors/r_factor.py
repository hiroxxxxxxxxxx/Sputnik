"""
R因子（Real-Rate Stress）：GC系専用。実質金利ストレスの検知。

TIP の高値比ドローダウンで R0/R2 を判定する。R1廃止。二択のみ。
悪化は即時、復帰は confirm_days 連続確認。高高度・中高度と低高度で閾値テーブル切り替え。
定義書「4-2-1-4 R因子（Real-Rate Stress：GC系）」参照。
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from avionics.data.signals import AltitudeRegime
from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle


class RFactor(BaseFactor):
    """
    R因子（Real-Rate Stress）：GC系専用。

    R2発動（即）: 高値比ドローダウンが閾値以下（高度別）。
    R0復帰（2日確認）: 高値比が復帰閾値以内を維持（高度別）。
    定義書「4-2-1-4」「0-4」参照。
    """

    def __init__(
        self,
        name: str,
        thresholds: dict,
        altitude: AltitudeRegime,
        history_size: int = 64,
    ) -> None:
        """
        R因子を初期化する。

        :param name: 表示用ラベル（例: "R"）。
        :param thresholds: しきい値辞書（drawdown_*_L2, drawdown_*_L0, confirm_days）。factors_config.get_r_thresholds で注入。
        :param history_size: レベル履歴バッファ長
        定義書「4-2-1-4 R因子」参照。
        """
        self.thresholds: dict = dict(thresholds)
        self._altitude: AltitudeRegime = altitude
        super().__init__(name=name, levels=[0, 2], history_size=history_size)

    def _drawdown_L2(self, altitude: AltitudeRegime) -> float:
        """R2発動閾値（高値比。例: -0.025）。"""
        key = f"drawdown_{altitude}_L2"
        return float(self.thresholds[key])

    def _drawdown_L0(self, altitude: AltitudeRegime) -> float:
        """R0復帰判定の上限（高値比。例: -0.015 なら -1.5%以内）。"""
        key = f"drawdown_{altitude}_L0"
        return float(self.thresholds[key])

    def _count_recovery_satisfied_days(
        self,
        daily_history_tip: tuple,
        altitude: AltitudeRegime,
    ) -> int:
        """基準日から遡り、tip_drawdown >= L0 の連続日数を返す。daily_history_tip は newest first。(date, drawdown)。"""
        L0 = self._drawdown_L0(altitude)
        count = 0
        for row in daily_history_tip:
            if len(row) >= 2 and row[1] >= L0:
                count += 1
            else:
                break
        return count

    def get_recovery_progress_from_bundle(self, symbol: str, bundle: Any) -> Optional[tuple[int, int]]:
        """bundle の liquidity_tip から復帰 x/N を算出。"""
        tip = getattr(bundle, "liquidity_tip", None)
        if not tip:
            return None
        daily_history_tip = getattr(tip, "daily_history_tip", ()) or ()
        altitude = self._altitude
        count = self._count_recovery_satisfied_days(daily_history_tip, altitude) if daily_history_tip else 0
        confirm = int(self.thresholds["confirm_days"])
        return (min(count, confirm), confirm)

    async def apply_signal_bundle(
        self, symbol: Optional[str], bundle: "SignalBundle"
    ) -> None:
        lt = getattr(bundle, "liquidity_tip", None)
        if lt is not None:
            await self.update_from_signals(
                altitude=self._altitude,
                tip_drawdown_from_high=lt.tip_drawdown_from_high if lt.tip_drawdown_from_high is not None else -0.001,
                daily_history_tip=getattr(lt, "daily_history_tip", ()),
            )

    async def update_from_signals(
        self,
        altitude: AltitudeRegime,
        tip_drawdown_from_high: float,
        daily_history_tip: tuple = (),
    ) -> LevelType:
        """
        事前計算済みシグナル（LiquiditySignals 相当：tip_drawdown_from_high）から R レベルを更新する。

        R2発動（即）: tip_drawdown_from_high <= drawdown_L2（高度別）。
        R0復帰: tip_drawdown_from_high >= drawdown_L0 を confirm_days 連続維持（ステートレス）。
        定義書「0-4」「4-2-1-4」参照。
        """
        confirm_days = int(self.thresholds["confirm_days"])
        L2 = self._drawdown_L2(altitude)
        L0 = self._drawdown_L0(altitude)

        r2_triggered = tip_drawdown_from_high <= L2
        r0_condition_met = tip_drawdown_from_high >= L0
        recovery_satisfied = (
            self._count_recovery_satisfied_days(daily_history_tip, altitude)
            if daily_history_tip
            else 0
        )

        if r2_triggered:
            self.downgrade(2)
            return 2

        if self.level == 2:
            await self.upgrade(
                0,
                confirm_days,
                recovery_confirm_satisfied_days=recovery_satisfied,
                condition_met=r0_condition_met,
            )
        return self.level
