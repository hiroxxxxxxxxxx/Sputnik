"""
S因子（タコメーター：SPAN乖離率）。入力は Layer 2 の出力（シグナル）のみ。
定義書「4-2-2-2 S因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle


class SFactor(BaseFactor):
    """
    S因子（タコメーター：SPAN乖離率）の計器クラス。

    現在の証拠金密度と基準証拠金密度の比率から S0/S1/S2 を判定する。
    悪化は即時、復帰は閾値ごとの確認日数を要求する。
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
        return await self._apply_two_level_ratio(
            span_ratio,
            lv2_on=float(t["S2_on"]),
            lv2_off=float(t["S2_off"]),
            lv1_on=float(t["S1_on"]),
            lv1_off=float(t["S1_off"]),
            lv2_confirm_days=int(t["S2_confirm_days"]),
            lv1_confirm_days=int(t["S1_confirm_days"]),
        )
