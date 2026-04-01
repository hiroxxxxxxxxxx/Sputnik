"""
S因子（タコメーター：SPAN乖離率）。入力は Layer 2 の出力（シグナル）のみ。
定義書「4-2-2-2 S因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import AltitudeRegime, SignalBundle


def s_step_level(prev: LevelType, span_ratio: float, thresholds: dict) -> LevelType:
    """
    SPEC.md 3-1 S 因子表（発動・復帰とも即時、切上げ/切捨て＋バッファの on/off のみ）。

    日次連続日数や履歴畳み込みは用いない。入力は当該ティックの比率と閾値・前レベル（on/off 用）のみ。
    """
    t = thresholds
    s2_on = float(t["S2_on"])
    s2_off = float(t["S2_off"])
    s1_on = float(t["S1_on"])
    s1_off = float(t["S1_off"])
    s_up = math.ceil(span_ratio * 100.0) / 100.0
    s_down = math.floor(span_ratio * 100.0) / 100.0
    if prev == 2:
        return 1 if s_down < s2_off else 2
    if prev == 1:
        if s_up >= s2_on:
            return 2
        if s_down < s1_off:
            return 0
        return 1
    if s_up >= s2_on:
        return 2
    if s_up >= s1_on:
        return 1
    return 0


class SFactor(BaseFactor):
    """
    S因子（タコメーター：SPAN乖離率）の計器クラス。

    現在の証拠金密度と基準証拠金密度の比率から S0/S1/S2 を判定する。
    悪化・復帰とも即時。確認日数は使わず、on/off バッファでヒステリシスを実現する。
    発動判定は小数点第2位切上げ、復帰判定は小数点第2位切捨てを適用する。
    閾値は factors_config.get_s_thresholds(config) で注入すること。
    定義書「4-2-2-2 S因子（タコメーター：SPAN乖離率）」セクション参照。
    """

    def __init__(self, thresholds: dict, history_size: int = 64) -> None:
        self._thresholds: dict = dict(thresholds)
        super().__init__(name="S", levels=[0, 1, 2], history_size=history_size)

    async def apply_signal_bundle(
        self,
        symbol: Optional[str],
        bundle: "SignalBundle",
        *,
        altitude: "AltitudeRegime",
    ) -> None:
        cap = getattr(bundle, "capital_signals", None)
        if cap is not None:
            await self.update_from_ratio(cap.span_ratio)

    async def update_from_ratio(self, span_ratio: float) -> LevelType:
        """SPAN乖離率からSレベルを更新する。定義書「0-4」「4-2-2-2」参照。"""
        nxt = s_step_level(self.level, span_ratio, self._thresholds)
        self.assign_level_from_computation(nxt)
        return self.level
