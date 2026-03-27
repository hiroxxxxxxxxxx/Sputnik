"""
S因子（タコメーター：SPAN乖離率）。入力は Layer 2 の出力（シグナル）のみ。
定義書「4-2-2-2 S因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle


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
        self, symbol: Optional[str], bundle: "SignalBundle"
    ) -> None:
        cap = getattr(bundle, "capital_signals", None)
        if cap is not None:
            await self.update_from_ratio(cap.span_ratio)

    async def update_from_ratio(self, span_ratio: float) -> LevelType:
        """SPAN乖離率からSレベルを更新する。定義書「0-4」「4-2-2-2」参照。"""
        t = self._thresholds
        s2_on = float(t["S2_on"])
        s2_off = float(t["S2_off"])
        s1_on = float(t["S1_on"])
        s1_off = float(t["S1_off"])

        s_up = math.ceil(span_ratio * 100.0) / 100.0
        s_down = math.floor(span_ratio * 100.0) / 100.0

        current = self.level
        if current == 2:
            candidate: LevelType = 1 if s_down < s2_off else 2
        elif current == 1:
            if s_up >= s2_on:
                candidate = 2
            elif s_down < s1_off:
                candidate = 0
            else:
                candidate = 1
        else:
            if s_up >= s2_on:
                candidate = 2
            elif s_up >= s1_on:
                candidate = 1
            else:
                candidate = 0

        if candidate > self.level:
            self.downgrade(candidate)
        elif candidate < self.level:
            self.level = candidate
            self.record_level()
            self.reset_confirmation()
        else:
            self.record_level()
        return self.level
