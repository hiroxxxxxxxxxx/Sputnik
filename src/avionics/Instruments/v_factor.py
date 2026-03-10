"""
V因子（Volatility Stress）：ボラティリティストレス計器。

銘柄に依存せず、注入されたしきい値（高度レジーム別）に従って V0/V1/V2 を判定する。
入力は Layer 2 の出力（シグナル）のみ。Raw Data を直接参照しない。
しきい値は設定ファイルから注入。定義書「4-2-1-2 V因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Literal, Optional, TYPE_CHECKING

import ib_async  # noqa: F401

from .base_factor import BaseFactor, BufferCondition, LevelType

if TYPE_CHECKING:
    from .signals import VolatilitySignal


AltitudeRegime = Literal["high_mid", "low"]


class VFactor(BaseFactor):
    """
    V因子（Volatility Stress）：ボラティリティストレス計器。

    銘柄名は持たず、注入されたしきい値（高度別）のみで判定する。
    悪化は即時、復帰は確認日数＋任意バッファ条件。
    定義書「4-2-1-2」「0-4」参照。
    """

    def __init__(
        self,
        name: str,
        thresholds: dict,
        history_size: int = 64,
    ) -> None:
        """
        V因子を初期化する。

        :param name: 表示用ラベル（例: "V_NQ"）。銘柄の「意味」は持たない。
        :param thresholds: 高度レジーム別しきい値。{"high_mid": {...}, "low": {...}}。
        :param history_size: レベル履歴バッファ長
        定義書「3-1 PFD」「4-2-1-2 V因子」参照。
        """
        self._thresholds_by_altitude: dict = dict(thresholds)
        self._last_recovery_satisfied_days: Optional[int] = None
        self._last_recovery_required_days: Optional[int] = None
        super().__init__(name=name, levels=[0, 1, 2], history_size=history_size)

    def _get_thresholds(self, altitude: AltitudeRegime) -> dict:
        """指定高度のしきい値辞書を返す。factors_config.get_v_thresholds() で完全な辞書を渡すこと。"""
        if altitude not in self._thresholds_by_altitude:
            raise KeyError(
                f"VFactor thresholds missing key {altitude!r}. "
                "Use factors_config.get_v_thresholds(config, symbol) for full dict."
            )
        return self._thresholds_by_altitude[altitude]

    def recovery_confirm_progress(self) -> Optional[tuple[int, int]]:
        """復帰ヒステリシスの x/N。シグナル由来の値を表示用に保持。"""
        if self._last_recovery_satisfied_days is None or self._last_recovery_required_days is None:
            return None
        return (self._last_recovery_satisfied_days, self._last_recovery_required_days)

    async def update(self) -> None:
        """
        最新のボラティリティ指数から V レベルを更新する。

        未注入時は安全なデフォルトで update_from_index を呼ぶ。
        定義書「3-1 PFD」「4-2-1-2 V因子」参照。
        """
        await self.update_from_index(
            index_value=25.0,
            altitude="high_mid",
            buffer_condition_v1_to_v0=None,
        )

    async def update_from_volatility_signal(
        self,
        signal: VolatilitySignal,
        buffer_condition_v1_to_v0: Optional[BufferCondition] = None,
    ) -> LevelType:
        """
        Layer 2 の VolatilitySignal から V レベルを更新する。

        因子は Layer 2 の出力のみを入力とする（定義書 4-2）。
        V1→V0復帰時は SPEC 4-2-1-2 の 1hノックインを適用する。
        呼び出し元が buffer_condition を渡さない場合は signal.v1_to_v0_knock_in_ok を用いる。
        """
        if buffer_condition_v1_to_v0 is None:
            buffer_condition_v1_to_v0 = lambda _f, _l: signal.is_intraday_condition_met
        return await self.update_from_index(
            index_value=signal.index_value,
            altitude=signal.altitude,
            buffer_condition_v1_to_v0=buffer_condition_v1_to_v0,
            recovery_confirm_satisfied_days_v1_off=signal.recovery_confirm_satisfied_days_v1_off,
            recovery_confirm_satisfied_days_v2_off=signal.recovery_confirm_satisfied_days_v2_off,
        )

    async def update_from_index(
        self,
        index_value: float,
        altitude: AltitudeRegime,
        buffer_condition_v1_to_v0: Optional[BufferCondition] = None,
        *,
        recovery_confirm_satisfied_days_v1_off: Optional[int] = None,
        recovery_confirm_satisfied_days_v2_off: Optional[int] = None,
    ) -> LevelType:
        """
        VXN/GVZ 相当の指数値（Layer 2 出力）から V レベルを更新する。

        復帰はシグナル由来の連続日数で一発判定（docs/recovery_confirm_spec_options.md）。
        recovery_confirm_satisfied_days_* が渡されない場合は従来の upgrade() で判定。
        """
        thresholds = self._get_thresholds(altitude)
        current = self.level
        v = index_value

        candidate: LevelType = current

        if v >= thresholds["V2_on"]:
            candidate = 2
        elif current == 2 and v < thresholds["V1_off"]:
            candidate = 0
        elif current == 2 and v < thresholds["V2_off"]:
            candidate = 1
        elif v >= thresholds["V1_on"]:
            candidate = max(candidate, 1)
        elif current == 1 and v < thresholds["V1_off"]:
            candidate = 0

        if candidate > self.level:
            self.downgrade(candidate)
            self._last_recovery_satisfied_days = None
            self._last_recovery_required_days = None
        elif candidate < self.level:
            use_signal_based = (
                recovery_confirm_satisfied_days_v1_off is not None
                and recovery_confirm_satisfied_days_v2_off is not None
            )
            if use_signal_based:
                if self.level == 2 and candidate == 1:
                    required = int(thresholds["V2_confirm_days"])
                    if recovery_confirm_satisfied_days_v2_off >= required:
                        self.level = 1
                        self.record_level()
                        self.reset_confirmation()
                        self._last_recovery_satisfied_days = None
                        self._last_recovery_required_days = None
                    else:
                        self._last_recovery_satisfied_days = recovery_confirm_satisfied_days_v2_off
                        self._last_recovery_required_days = required
                elif self.level == 1 and candidate == 0:
                    required = int(thresholds["V1_confirm_days"])
                    buf_ok = buffer_condition_v1_to_v0 is not None
                    if buf_ok:
                        result = buffer_condition_v1_to_v0(self, 0)
                        if isinstance(result, Awaitable):
                            result = await result
                        buf_ok = bool(result)
                    if recovery_confirm_satisfied_days_v1_off >= required and buf_ok:
                        self.level = 0
                        self.record_level()
                        self.reset_confirmation()
                        self._last_recovery_satisfied_days = None
                        self._last_recovery_required_days = None
                    else:
                        self._last_recovery_satisfied_days = recovery_confirm_satisfied_days_v1_off
                        self._last_recovery_required_days = required
                else:
                    await self.upgrade(candidate, confirm_days=1)
                    self._last_recovery_satisfied_days = None
                    self._last_recovery_required_days = None
            else:
                if self.level == 2 and candidate == 1:
                    await self.upgrade(candidate, confirm_days=thresholds["V2_confirm_days"])
                elif self.level == 1 and candidate == 0:
                    await self.upgrade(
                        candidate,
                        confirm_days=thresholds["V1_confirm_days"],
                        buffer_condition=buffer_condition_v1_to_v0,
                    )
                else:
                    await self.upgrade(candidate, confirm_days=1)
                self._last_recovery_satisfied_days = None
                self._last_recovery_required_days = None
        else:
            self.record_level()
            self._last_recovery_satisfied_days = None
            self._last_recovery_required_days = None

        return self.level
