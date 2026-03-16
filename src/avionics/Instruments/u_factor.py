"""
U因子（Gメーター：MM/NLV）。入力は Layer 2 の出力（シグナル）のみ。
定義書「4-2-2-1 U因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import CapitalSignals, SignalBundle


class UFactor(BaseFactor):
    """
    U因子（Gメーター：MM/NLV）の計器クラス。

    証拠金使用率（MM/NLV）に基づき C0/C1/C2 を判定する。
    悪化は即時、復帰は閾値ごとの確認日数を要求する。
    閾値は factors_config.get_u_thresholds(config) で注入すること。
    定義書「4-2-2-1 U因子（Gメーター：MM/NLV）」セクション参照。
    """

    def __init__(self, thresholds: dict, history_size: int = 64) -> None:
        """
        U因子を初期化する。

        :param thresholds: しきい値辞書（C2_on, C2_off, C1_on, C1_off, C2_confirm_days, C1_confirm_days）。config/factors.toml の [U] から注入。
        :param history_size: レベル履歴バッファ長

        定義書「3-1 PFD」「4-2-2-1 U因子」参照。
        """
        self._thresholds: dict = dict(thresholds)
        super().__init__(name="U", levels=[0, 1, 2], history_size=history_size)

    async def update(self) -> None:
        """
        最新のMM/NLVからUレベルを更新する。

        FlightController 等から呼ばれる共通エントリ。実データは上位で注入する想定のため、
        未注入時は安全なデフォルトで update_from_ratio() を呼ぶ。
        定義書「3-1 PFD」「4-2-2-1 U因子」参照。
        """
        await self.update_from_ratio(0.3)

    async def update_from_signal_bundle(
        self, symbol: Optional[str], bundle: "SignalBundle"
    ) -> None:
        cap = getattr(bundle, "capital_signals", None)
        if cap is not None:
            await self.update_from_ratio(cap.mm_over_nlv)
        else:
            await self.update()

    async def update_from_capital_signals(self, signals: CapitalSignals) -> LevelType:
        """
        Layer 2 の CapitalSignals から U レベルを更新する。

        因子は Layer 2 の出力のみを入力とする（定義書 4-2）。
        """
        return await self.update_from_ratio(signals.mm_over_nlv)

    async def update_from_ratio(self, mm_over_nlv: float) -> LevelType:
        """
        MM/NLV比率（Layer 2 出力）からUレベルを更新する。

        :param mm_over_nlv: 証拠金使用率（0.40 = 40% など）
        :return: 判定後のUレベル（0/1/2）

        悪化方向（C0→C1→C2）は `downgrade()` で即時反映し、
        改善方向（C2→C1→C0）は `upgrade()` で
        C2→C1は2日、C1→C0は3日連続確認を要求する。
        定義書「0-4」「4-2-2-1」参照。
        """
        current = self.level
        r = mm_over_nlv
        t = self._thresholds
        c2_on = float(t["C2_on"])
        c2_off = float(t["C2_off"])
        c1_on = float(t["C1_on"])
        c1_off = float(t["C1_off"])

        candidate: LevelType

        if current == 2:
            if r < c2_off:
                candidate = 1
            else:
                candidate = 2
        elif current == 1:
            if r >= c2_on:
                candidate = 2
            elif r < c1_off:
                candidate = 0
            elif r >= c1_on:
                candidate = 1
            else:
                candidate = 1
        else:  # current == 0
            if r >= c2_on:
                candidate = 2
            elif r >= c1_on:
                candidate = 1
            else:
                candidate = 0

        if candidate > self.level:
            self.downgrade(candidate)
        elif candidate < self.level:
            if self.level == 2 and candidate == 1:
                await self.upgrade(candidate, confirm_days=int(t["C2_confirm_days"]))
            elif self.level == 1 and candidate == 0:
                await self.upgrade(candidate, confirm_days=int(t["C1_confirm_days"]))
            else:
                await self.upgrade(candidate, confirm_days=1)
        else:
            self.record_level()

        return self.level

