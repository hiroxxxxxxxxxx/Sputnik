"""
V因子（Volatility Stress）：ボラティリティストレス計器。

銘柄に依存せず、注入されたしきい値（高度レジーム別）に従って V0/V1/V2 を判定する。
入力は Layer 2 の出力（シグナル）のみ。Raw Data を直接参照しない。
しきい値は設定ファイルから注入。定義書「4-2-1-2 V因子」「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Literal, Optional, TYPE_CHECKING

from .base_factor import BaseFactor, BufferCondition, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle, VolatilitySignal


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
        super().__init__(name=name, levels=[0, 1, 2], history_size=history_size)

    def _get_thresholds(self, altitude: AltitudeRegime) -> dict:
        """指定高度のしきい値辞書を返す。factors_config.get_v_thresholds() で完全な辞書を渡すこと。"""
        if altitude not in self._thresholds_by_altitude:
            raise KeyError(
                f"VFactor thresholds missing key {altitude!r}. "
                "Use factors_config.get_v_thresholds(config, symbol) for full dict."
            )
        return self._thresholds_by_altitude[altitude]

    def get_recovery_progress_from_bundle(self, symbol: str, bundle: Any) -> Optional[tuple[int, int]]:
        """bundle の volatility_signals[symbol] から復帰 x/N を算出。"""
        sig = getattr(bundle, "volatility_signals", {}).get(symbol)
        if not sig:
            return None
        th = self._get_thresholds(getattr(sig, "altitude", "high_mid"))
        if self.level == 2:
            required = int(th["V2_confirm_days"])
            satisfied = getattr(sig, "recovery_confirm_satisfied_days_v2_off", 0)
            return (min(satisfied, required), required)
        if self.level == 1:
            required = int(th["V1_confirm_days"])
            satisfied = getattr(sig, "recovery_confirm_satisfied_days_v1_off", 0)
            return (min(satisfied, required), required)
        return None

    async def apply_signal_bundle(
        self, symbol: Optional[str], bundle: "SignalBundle"
    ) -> None:
        vol = getattr(bundle, "volatility_signals", {}).get(symbol) if symbol else None
        if vol is not None:
            await self.update_from_volatility_signal(vol)

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
            recovery_confirm_satisfied_days_v1_off=signal.recovery_confirm_satisfied_days_v1_off,
            recovery_confirm_satisfied_days_v2_off=signal.recovery_confirm_satisfied_days_v2_off,
            buffer_condition_v1_to_v0=buffer_condition_v1_to_v0,
        )

    async def update_from_index(
        self,
        index_value: float,
        altitude: AltitudeRegime,
        recovery_confirm_satisfied_days_v1_off: int,
        recovery_confirm_satisfied_days_v2_off: int,
        buffer_condition_v1_to_v0: Optional[BufferCondition] = None,
    ) -> LevelType:
        """
        VXN/GVZ 相当の指数値（Layer 2 出力）から V レベルを更新する。ステートレス専用。

        復帰はシグナル由来の連続日数で一発判定（docs/archive/recovery_confirm_spec_options.md）。
        recovery_confirm_satisfied_days_* は呼び出し元（Layer 2 算出結果）で必ず渡すこと。
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
        elif candidate < self.level:
            if self.level == 2 and candidate == 1:
                required = int(thresholds["V2_confirm_days"])
                if recovery_confirm_satisfied_days_v2_off >= required:
                    self.level = 1
                    self.record_level()
                    self.reset_confirmation()
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
            else:
                await self.upgrade(
                    candidate,
                    confirm_days=1,
                    recovery_confirm_satisfied_days=1,
                )
        else:
            self.record_level()

        return self.level
