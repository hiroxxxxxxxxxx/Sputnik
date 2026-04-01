"""
R因子（Real-Rate Stress）：GC系専用。実質金利ストレスの検知。

TIP の高値比ドローダウンで R0/R2 を判定する。R1廃止。二択のみ。
悪化は即時、復帰は confirm_days 連続確認。高高度・中高度と低高度で閾値テーブル切り替え。
定義書「4-2-1-4 R因子（Real-Rate Stress：GC系）」参照。
"""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional, TYPE_CHECKING, Tuple

from avionics.data.signals import AltitudeRegime, TipDailyRow
from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle


def _r_recovery_days(prefix_newest_first: Tuple[TipDailyRow, ...], L0: float) -> int:
    count = 0
    for row in prefix_newest_first:
        if len(row) >= 2 and row[1] >= L0:
            count += 1
        else:
            break
    return count


def r_level_from_tip_history(
    rows_oldest_first: List[TipDailyRow],
    altitude: AltitudeRegime,
    thresholds: dict,
) -> LevelType:
    L2 = float(thresholds[f"drawdown_{altitude}_L2"])
    L0 = float(thresholds[f"drawdown_{altitude}_L0"])
    confirm_days = int(thresholds["confirm_days"])
    level: LevelType = 0
    for i, row in enumerate(rows_oldest_first):
        if len(row) < 2:
            break
        _d, dd = row[0], row[1]
        r2_triggered = dd <= L2
        r0_condition_met = dd >= L0
        prefix_nf = tuple(reversed(rows_oldest_first[: i + 1]))
        recovery = _r_recovery_days(prefix_nf, L0)
        if r2_triggered:
            level = 2
            continue
        if level == 2 and r0_condition_met and recovery >= confirm_days:
            level = 0
    return level


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
        history_size: int = 64,
    ) -> None:
        """
        R因子を初期化する。

        :param name: 表示用ラベル（例: "R"）。
        :param thresholds: しきい値辞書（drawdown_*_L2, drawdown_*_L0, confirm_days）。factors_config.get_r_thresholds で注入。
        :param history_size: レベル履歴バッファ長
        運用高度は apply_signal_bundle で毎回指定する（DB 由来）。
        定義書「4-2-1-4 R因子」参照。
        """
        self.thresholds: dict = dict(thresholds)
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

    def get_recovery_progress_from_bundle(
        self,
        symbol: str,
        bundle: Any,
        *,
        altitude: AltitudeRegime,
    ) -> Optional[tuple[int, int]]:
        """bundle の liquidity_tip から復帰 x/N を算出。"""
        tip = getattr(bundle, "liquidity_tip", None)
        if not tip:
            return None
        daily_history_tip = getattr(tip, "daily_history_tip", ()) or ()
        count = self._count_recovery_satisfied_days(daily_history_tip, altitude) if daily_history_tip else 0
        confirm = int(self.thresholds["confirm_days"])
        return (min(count, confirm), confirm)

    async def apply_signal_bundle(
        self,
        symbol: Optional[str],
        bundle: "SignalBundle",
        *,
        altitude: AltitudeRegime,
    ) -> None:
        lt = getattr(bundle, "liquidity_tip", None)
        if lt is not None:
            if lt.tip_drawdown_from_high is None:
                raise ValueError("RFactor requires liquidity_tip.tip_drawdown_from_high")
            rows = list(reversed(lt.daily_history_tip))
            if not rows:
                rows = [
                    (
                        date.min,
                        lt.tip_drawdown_from_high,
                    )
                ]
            level = r_level_from_tip_history(rows, altitude, self.thresholds)
            self.assign_level_from_computation(level)

    async def update_from_signals(
        self,
        altitude: AltitudeRegime,
        tip_drawdown_from_high: float,
        daily_history_tip: tuple = (),
    ) -> LevelType:
        """
        事前計算済みシグナルから R レベルを更新する（テスト用）。
        """
        rows = list(reversed(daily_history_tip))
        if not rows:
            rows = [(date.min, tip_drawdown_from_high)]
        level = r_level_from_tip_history(rows, altitude, self.thresholds)
        self.assign_level_from_computation(level)
        return level
