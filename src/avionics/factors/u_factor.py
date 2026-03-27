"""
U因子（Gメーター：MM/NLV）。入力は Layer 2 の出力（シグナル）のみ。
定義書「4-2-2-1 U因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle


class UFactor(BaseFactor):
    """
    U因子（Gメーター：MM/NLV）の計器クラス。

    証拠金使用率（MM/NLV）に基づき C0/C1/C2 を判定する。
    悪化・復帰とも即時。確認日数は使わず、on/off バッファでヒステリシスを実現する。
    閾値は factors_config.get_u_thresholds(config) で注入すること。
    定義書「4-2-2-1 U因子（Gメーター：MM/NLV）」セクション参照。
    """

    def __init__(self, thresholds: dict, history_size: int = 64) -> None:
        self._thresholds: dict = dict(thresholds)
        super().__init__(name="U", levels=[0, 1, 2], history_size=history_size)

    async def apply_signal_bundle(
        self, symbol: Optional[str], bundle: "SignalBundle"
    ) -> None:
        cap = getattr(bundle, "capital_signals", None)
        if cap is not None:
            await self.update_from_ratio(cap.mm_over_nlv)

    async def update_from_ratio(self, mm_over_nlv: float) -> LevelType:
        """MM/NLV比率からUレベルを更新する。定義書「0-4」「4-2-2-1」参照。"""
        t = self._thresholds
        c2_on = float(t["C2_on"])
        c2_off = float(t["C2_off"])
        c1_on = float(t["C1_on"])
        c1_off = float(t["C1_off"])

        current = self.level
        if current == 2:
            candidate: LevelType = 1 if mm_over_nlv < c2_off else 2
        elif current == 1:
            if mm_over_nlv >= c2_on:
                candidate = 2
            elif mm_over_nlv < c1_off:
                candidate = 0
            else:
                candidate = 1
        else:
            if mm_over_nlv >= c2_on:
                candidate = 2
            elif mm_over_nlv >= c1_on:
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
