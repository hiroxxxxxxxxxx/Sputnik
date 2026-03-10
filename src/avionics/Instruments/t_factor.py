"""
T因子（Trend）：銘柄固有のトレンド判定。サブスクリプション方式に準拠。

担当銘柄のトレンド（up/down/flat）は Layer 2 の Signal であり、T はその Signal を
入力に T0/T2 を出力する。出力 level は同期制御層（T 相関）の入力として扱う。
Raw Data を直接参照しない。NQ/GC をセットで見る「一括監視」は廃止。
定義書「4-2-1-4 T因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import Literal

from .base_factor import BaseFactor, LevelType


TrendType = Literal["up", "down", "flat"]


class TFactor(BaseFactor):
    """
    T因子（Trend）：銘柄固有のトレンド判定。

    担当銘柄のトレンドだけを監視する。down → T2（即時）、up/flat → T0（復帰は継続確認）。
    非対称ヒステリシス厳守。定義書「4-2-1-4」「0-4」参照。
    """

    def __init__(self, symbol: str, thresholds: dict, history_size: int = 64) -> None:
        """
        T因子を初期化する。

        :param symbol: 担当銘柄（"NQ" / "GC" 等）。サブスクリプションでこの銘柄の M にのみ寄与する。
        :param thresholds: しきい値辞書（confirm_days）。config/factors.toml の [T] から注入。
        :param history_size: レベル履歴バッファ長
        定義書「4-2-1-4 T因子」参照。
        """
        self.symbol: str = symbol
        self._thresholds: dict = dict(thresholds)
        super().__init__(
            name=f"T_{symbol}",
            levels=[0, 2],
            history_size=history_size,
        )

    async def update(self) -> None:
        """
        Cockpit.update_all() から呼ばれる主エントリ。

        トレンドは update_all(signal_bundle) で PriceSignals.trend が渡されるか、
        呼び出し元が apply_trend(trend) を直接呼ぶ。未注入時はレベルを変更せず record_level のみ。
        定義書「3-1 PFD」「4-2-1-4」参照。
        """
        self.record_level()

    async def apply_trend(self, trend: TrendType) -> LevelType:
        """
        銘柄別トレンド Signal（Layer 2）を反映し、ヒステリシスを伴ってレベルを更新する。

        :param trend: 担当銘柄のトレンド Signal（"up" / "down" / "flat"）
        :return: 更新後のレベル（0 または 2）

        down → T2 は即時降格。T2 → T0 は閾値 confirm_days の期間連続 up/flat 確認後に昇格。
        定義書「0-4」「4-2-1-4」参照。
        """
        new_level: LevelType = 2 if trend == "down" else 0
        confirm_days = int(self._thresholds["confirm_days"])

        if new_level > self.level:
            self.downgrade(new_level)
        elif new_level < self.level:
            await self.upgrade(new_level, confirm_days=confirm_days)
        else:
            self.record_level()

        return self.level
