"""
V因子（Volatility Stress）：ボラティリティストレス計器。

銘柄に依存せず、注入されたしきい値（高度レジーム別）に従って V0/V1/V2 を判定する。
入力は Layer 2 の出力（シグナル）のみ。Raw Data を直接参照しない。
しきい値は設定ファイルから注入。定義書「4-2-1-2 V因子」「4-2 情報の階層構造」参照。

レベルは VolatilitySignal.index_history（as_of までの日次指数・日付昇順）を畳み込んだ結果のみとし、
プロセス内の前回 self.level や upgrade の内部カウンタに依存しない（完全ステートレス）。
V2→V0 の直接遷移は行わない（V2_off 経由で V1、V1 は V1_off＋確認＋ノックインで V0）。
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Optional, TYPE_CHECKING

from avionics.compute import _count_consecutive_days_below
from avionics.data.signals import AltitudeRegime
from .base_factor import BaseFactor, BufferCondition, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle, VolatilitySignal


def _v_transition_step(
    prev: LevelType,
    v: float,
    th: dict,
    sat_v1: int,
    sat_v2: int,
    knock_in: bool,
) -> LevelType:
    """1 日分の指数 v と復帰カウントに対する次レベル（畳み込み用・純関数）。"""
    V2_on = float(th["V2_on"])
    V2_off = float(th["V2_off"])
    V1_on = float(th["V1_on"])
    V1_off = float(th["V1_off"])
    v2cd = int(th["V2_confirm_days"])
    v1cd = int(th["V1_confirm_days"])

    candidate: LevelType = prev
    if v >= V2_on:
        candidate = 2
    elif prev == 2 and v < V2_off:
        candidate = 1
    elif v >= V1_on:
        candidate = max(candidate, 1)
    elif prev == 1 and v < V1_off:
        candidate = 0

    if candidate > prev:
        return candidate
    if candidate < prev:
        if prev == 2 and candidate == 1:
            return 1 if sat_v2 >= v2cd else 2
        if prev == 1 and candidate == 0:
            return 0 if (sat_v1 >= v1cd and knock_in) else 1
        return prev
    return prev


async def _v_level_from_index_history_async(
    index_history: tuple[tuple[Any, float], ...],
    th: dict,
    *,
    last_knock_in_from_signal: bool,
    buffer_condition_v1_to_v0: Optional[BufferCondition],
    factor: BaseFactor,
) -> LevelType:
    """
    index_history を日付昇順で畳み込み、最終日に SPEC 4-2-1-2 の 1h ノックインを適用する。

    過去日は日次系列のみのため V1→V0 のノックインを満たしたとみなす（intraday 非保持のため）。
    最終日は signal の v1_to_v0_knock_in_ok または buffer_condition を使う。
    """
    if not index_history:
        raise ValueError("VolatilitySignal.index_history must not be empty")

    n = len(index_history)
    level: LevelType = 0
    for i, (_d, v) in enumerate(index_history):
        series_upto = list(index_history[: i + 1])
        sat_v1 = _count_consecutive_days_below(series_upto, float(th["V1_off"]))
        sat_v2 = _count_consecutive_days_below(series_upto, float(th["V2_off"]))
        is_last = i == n - 1

        if is_last and buffer_condition_v1_to_v0 is not None:
            pretend = _v_transition_step(
                level, float(v), th, sat_v1, sat_v2, knock_in=True,
            )
            if level == 1 and pretend == 0:
                buf = buffer_condition_v1_to_v0(factor, 0)
                if isinstance(buf, Awaitable):
                    buf = await buf
                knock_eff = bool(buf)
            else:
                knock_eff = last_knock_in_from_signal
        elif is_last:
            knock_eff = last_knock_in_from_signal
        else:
            knock_eff = True

        level = _v_transition_step(
            level, float(v), th, sat_v1, sat_v2, knock_eff,
        )
    return level


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
        :param thresholds: 高度レジーム別しきい値（high/mid/low 全キー）。
        :param history_size: レベル履歴バッファ長
        運用高度は apply_signal_bundle に渡すたびに指定する（DB 由来）。
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

    def get_recovery_progress_from_bundle(
        self,
        symbol: str,
        bundle: Any,
        *,
        altitude: AltitudeRegime,
    ) -> Optional[tuple[int, int]]:
        """bundle の volatility_signals[symbol] から復帰 x/N を算出。"""
        sig = getattr(bundle, "volatility_signals", {}).get(symbol)
        if not sig:
            return None
        th = self._get_thresholds(altitude)
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
        self,
        symbol: Optional[str],
        bundle: "SignalBundle",
        *,
        altitude: AltitudeRegime,
    ) -> None:
        vol = getattr(bundle, "volatility_signals", {}).get(symbol) if symbol else None
        if vol is not None:
            await self.update_from_volatility_signal(vol, altitude=altitude)

    async def update_from_volatility_signal(
        self,
        signal: "VolatilitySignal",
        *,
        altitude: AltitudeRegime,
        buffer_condition_v1_to_v0: Optional[BufferCondition] = None,
    ) -> LevelType:
        """
        Layer 2 の VolatilitySignal から V レベルを更新する。

        index_history が必須。V1→V0復帰時は SPEC 4-2-1-2 の 1hノックインを最終日に適用する。
        呼び出し元が buffer_condition を渡さない場合は signal.v1_to_v0_knock_in_ok を用いる。
        """
        hist = signal.index_history
        if not hist:
            raise ValueError(
                "VolatilitySignal.index_history is required for stateless V; "
                "ensure build_signal_bundle / compute_volatility_signal_from_snapshot populates it."
            )
        if buffer_condition_v1_to_v0 is None:
            buffer_condition_v1_to_v0 = lambda _f, _l: signal.v1_to_v0_knock_in_ok
        th = self._get_thresholds(altitude)
        level = await _v_level_from_index_history_async(
            hist,
            th,
            last_knock_in_from_signal=signal.v1_to_v0_knock_in_ok,
            buffer_condition_v1_to_v0=buffer_condition_v1_to_v0,
            factor=self,
        )
        self.assign_level_from_computation(level)
        return level

    async def update_from_index(
        self,
        index_value: float,
        altitude: AltitudeRegime,
        recovery_confirm_satisfied_days_v1_off: int,
        recovery_confirm_satisfied_days_v2_off: int,
        buffer_condition_v1_to_v0: Optional[BufferCondition] = None,
    ) -> LevelType:
        """
        非推奨: 単一日のみの履歴で畳み込む（テスト互換用）。

        運用は VolatilitySignal.index_history を用いること。
        """
        _ = recovery_confirm_satisfied_days_v1_off
        _ = recovery_confirm_satisfied_days_v2_off
        from avionics.data.signals import VolatilitySignal

        async def no_buffer(_f: BaseFactor, _lvl: LevelType) -> bool:
            return False

        buf = buffer_condition_v1_to_v0
        if buf is None:
            eff_buf: BufferCondition = no_buffer
        else:

            async def eff_buf(f: BaseFactor, lvl: LevelType) -> bool:
                r = buf(f, lvl)
                if isinstance(r, Awaitable):
                    return bool(await r)
                return bool(r)

        sig = VolatilitySignal(
            index_value=index_value,
            index_history=((self._placeholder_date(), index_value),),
            v1_to_v0_knock_in_ok=False,
        )
        return await self.update_from_volatility_signal(
            sig,
            altitude=altitude,
            buffer_condition_v1_to_v0=eff_buf,
        )

    @staticmethod
    def _placeholder_date() -> Any:
        from datetime import date

        return date(1970, 1, 1)
