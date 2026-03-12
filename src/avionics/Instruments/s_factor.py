"""
S因子（タコメーター：SPAN乖離率）。入力は Layer 2 の出力（シグナル）のみ。
定義書「4-2-2-2 S因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from .signals import CapitalSignals


class SFactor(BaseFactor):
    """
    S因子（タコメーター：SPAN乖離率）の計器クラス。

    現在の証拠金密度と基準証拠金密度の比率から S0/S1/S2 を判定する。
    悪化は即時、復帰は閾値ごとの確認日数を要求する。
    閾値は factors_config.get_s_thresholds(config) で注入すること。
    定義書「4-2-2-2 S因子（タコメーター：SPAN乖離率）」セクション参照。
    """

    def __init__(self, thresholds: dict, history_size: int = 64) -> None:
        """
        S因子を初期化する。

        :param thresholds: しきい値辞書（S2_on, S2_off, S1_on, S1_off, S2_confirm_days, S1_confirm_days）。config/factors.toml の [S] から注入。
        :param history_size: レベル履歴バッファ長

        定義書「3-1 PFD」「4-2-2-2 S因子」参照。
        """
        self._thresholds: dict = dict(thresholds)
        super().__init__(name="S", levels=[0, 1, 2], history_size=history_size)

    async def update(self) -> None:
        """
        最新のSPAN乖離率からSレベルを更新する。

        FlightController 等から呼ばれる共通エントリ。実データは上位で注入する想定のため、
        未注入時は安全なデフォルトで update_from_ratio() を呼ぶ。
        定義書「3-1 PFD」「4-2-2-2 S因子」参照。
        """
        await self.update_from_ratio(1.0)

    async def update_from_capital_signals(self, signals: CapitalSignals) -> LevelType:
        """
        Layer 2 の CapitalSignals から S レベルを更新する。

        因子は Layer 2 の出力のみを入力とする（定義書 4-2）。
        """
        return await self.update_from_ratio(signals.span_ratio)

    async def update_from_ratio(self, span_ratio: float) -> LevelType:
        """
        SPAN乖離率（Layer 2 出力）からSレベルを更新する。

        :param span_ratio: S = Current Density / Base Density
        :return: 判定後のSレベル（0/1/2）

        悪化方向（S0→S1→S2）は `downgrade()` で即時反映し、
        改善方向（S2→S1→S0）は `upgrade()` で
        S2→S1は2日、S1→S0は3日連続確認を要求する。
        定義書「0-4」「4-2-2-2」参照。
        """
        current = self.level
        s = span_ratio
        t = self._thresholds
        s2_on = float(t["S2_on"])
        s2_off = float(t["S2_off"])
        s1_on = float(t["S1_on"])
        s1_off = float(t["S1_off"])

        candidate: LevelType

        if current == 2:
            if s < s2_off:
                candidate = 1
            else:
                candidate = 2
        elif current == 1:
            if s >= s2_on:
                candidate = 2
            elif s < s1_off:
                candidate = 0
            elif s >= s1_on:
                candidate = 1
            else:
                candidate = 1
        else:  # current == 0
            if s >= s2_on:
                candidate = 2
            elif s >= s1_on:
                candidate = 1
            else:
                candidate = 0

        if candidate > self.level:
            self.downgrade(candidate)
        elif candidate < self.level:
            if self.level == 2 and candidate == 1:
                await self.upgrade(candidate, confirm_days=int(t["S2_confirm_days"]))
            elif self.level == 1 and candidate == 0:
                await self.upgrade(candidate, confirm_days=int(t["S1_confirm_days"]))
            else:
                await self.upgrade(candidate, confirm_days=1)
        else:
            self.record_level()

        return self.level

