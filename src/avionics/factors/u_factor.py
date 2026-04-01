"""
U因子（Gメーター：MM/NLV）。入力は Layer 2 の出力（シグナル）のみ。
定義書「4-2-2-1 U因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import AltitudeRegime, SignalBundle


def u_step_level(prev: LevelType, mm_over_nlv: float, thresholds: dict) -> LevelType:
    """
    SPEC.md 3-1 U 因子表（発動・復帰とも即時、バッファ幅の on/off のみ）。

    日次連続日数や価格履歴の畳み込みは用いない。入力は当該ティックの MM/NLV と閾値・前レベル
    （on/off ヒステリシス用）のみ。
    """
    t = thresholds
    c2_on = float(t["C2_on"])
    c2_off = float(t["C2_off"])
    c1_on = float(t["C1_on"])
    c1_off = float(t["C1_off"])
    if prev == 2:
        return 1 if mm_over_nlv < c2_off else 2
    if prev == 1:
        if mm_over_nlv >= c2_on:
            return 2
        if mm_over_nlv < c1_off:
            return 0
        return 1
    if mm_over_nlv >= c2_on:
        return 2
    if mm_over_nlv >= c1_on:
        return 1
    return 0


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
        self,
        symbol: Optional[str],
        bundle: "SignalBundle",
        *,
        altitude: "AltitudeRegime",
    ) -> None:
        cap = getattr(bundle, "capital_signals", None)
        if cap is not None:
            await self.update_from_ratio(cap.mm_over_nlv)

    async def update_from_ratio(self, mm_over_nlv: float) -> LevelType:
        """MM/NLV比率からUレベルを更新する。定義書「0-4」「4-2-2-1」参照。"""
        nxt = u_step_level(self.level, mm_over_nlv, self._thresholds)
        self.assign_level_from_computation(nxt)
        return self.level
