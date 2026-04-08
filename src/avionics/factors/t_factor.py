"""
T因子（Trend）：銘柄固有のトレンド判定。サブスクリプション方式に準拠。

担当銘柄のトレンド（up/down/flat）は Layer 2 の Signal であり、T はその Signal を
入力に T0/T2 を出力する。出力 level は同期制御層（T 相関）の入力として扱う。
Raw Data を直接参照しない。NQ/GC をセットで見る「一括監視」は廃止。

SCL の T は復帰日数待機を持たない。down → T2・up/flat → T0 を即時に切り替える。
定義書「4-2-1-4 T因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import AltitudeRegime, SignalBundle


TrendType = Literal["up", "down", "flat"]


def t_level_from_trend(trend: TrendType) -> LevelType:
    """当季のトレンドシグナルから T レベルを返す（日次待機なし）。"""
    return 2 if trend == "down" else 0


class TFactor(BaseFactor):
    """
    T因子（Trend）：銘柄固有のトレンド判定。

    担当銘柄のトレンドだけを監視する。down → T2・up/flat → T0（いずれも即時）。
    定義書「4-2-1-4」「0-4」参照。
    """

    def __init__(self, symbol: str, thresholds: dict, history_size: int = 64) -> None:
        """
        T因子を初期化する。

        :param symbol: 担当銘柄（"NQ" / "GC" 等）。サブスクリプションでこの銘柄の M にのみ寄与する。
        :param thresholds: 将来の [T] 拡張用（現状未使用でも assembly から注入される）。
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

    async def apply_signal_bundle(
        self,
        symbol: Optional[str],
        bundle: "SignalBundle",
        *,
        altitude: "AltitudeRegime",
    ) -> None:
        price = getattr(bundle, "price_signals", {}).get(symbol) if symbol else None
        if price is not None:
            await self.apply_trend(price.trend)

    async def apply_trend(
        self,
        trend: TrendType,
        daily_history: tuple = (),
    ) -> LevelType:
        """
        銘柄別トレンド Signal（Layer 2）を反映する。

        down → T2、up/flat → T0（いずれも即時）。daily_history は互換のため受け取るが無視する。
        定義書「0-4」「4-2-1-4」参照。
        """
        _ = daily_history
        level = t_level_from_trend(trend)
        self.assign_level_from_computation(level)
        return self.level
