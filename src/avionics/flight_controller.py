"""
FlightController（計器層）：三層制御（個別・同期・制限）の算出に特化。レイヤー混合を避ける。

個別制御層・同期制御層・制限制御層を算出し、get_effective_level(symbol) で実行レベルを返す。
FlightControllerSignal で「計器の結論」をカプセル化し、Cockpit（管制層）の承認ゲートへ渡す。
定義書「3.フライトコントローラー」「4-2」「0-1-Ⅲ」参照。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .Instruments.signals import SignalBundle
from .mode import BOOST, CRUISE, EMERGENCY, ModeType


@dataclass
class FlightControllerSignal:
    """
    FlightController が出力する「計器の結論」をカプセル化したデータ構造。
    Cockpit（管制層）の承認ゲート（Manual/Auto）や Protocol 起動の入力となる。
    定義書「Phase 5 Telegram統合」Signal 定義参照。
    """

    throttle_level: int
    """0: Boost, 1: Cruise, 2: Emergency（get_effective_level と同一スケール）"""

    reason: str
    """判定理由（例: 「LCL 10%超」「SCL=2」「個別層 P=2」）。通知用。"""

    is_critical: bool
    """True なら FC での承認をスキップして即時プロトコル発火。現在は LCL>=2（制限層 Emergency）のみ。定義書で変更可。"""

    raw_metrics: Dict[str, Any]
    """P, V, C, R, T, U, S の生データ（通知用）。キーは因子名。"""

    recovery_metrics: Dict[str, str] = field(default_factory=dict)
    """復帰ヒステリシスの「x/N日目」。キーは因子名、値は "1/2" 等。Daily Report 用。"""


class FlightController:
    """
    計器層。個別制御層・同期制御層・制限制御層の三層のみで実行レベルを算出する。

    global_capital_factors（U,S）, symbol_factors（銘柄別 P,V,T,C/R）を登録し、
    get_effective_level(symbol) = max(個別, 同期, 制限) で実行レベルを返す。
    定義書「4-2」計器・「0-1-Ⅲ」抽象構造参照。
    """

    def __init__(
        self,
        *,
        global_market_factors: Optional[List[Any]] = None,
        global_capital_factors: Optional[List[Any]] = None,
        symbol_factors: Optional[Dict[str, List[Any]]] = None,
    ) -> None:
        """
        計器を初期化する。三層（個別・同期・制限）用の因子リストのみ受け付ける。

        :param global_market_factors: 全エンジン共通の個別制御用因子（未使用時は空で可）
        :param global_capital_factors: 全エンジン共通の制限制御層因子（U, S）
        :param symbol_factors: 銘柄別因子。{"NQ": [P,V,T,C], "GC": [P,V,T,R]} 等
        定義書「4-2」「0-1-Ⅲ」参照。
        """
        self._global_market_factors: List[Any] = list(global_market_factors or [])
        self._global_capital_factors: List[Any] = list(global_capital_factors or [])
        self._symbol_factors: Dict[str, List[Any]] = dict(symbol_factors or {})

    @property
    def use_subscription(self) -> bool:
        """三層方式で銘柄別に個別・同期・制限を算出する。常に True。"""
        return True

    def register_factor(self, group: str, factor: Any) -> None:
        """
        因子を登録する。

        :param group: "GLOBAL_M"（L）, "GLOBAL_C"（U,S）, "NQ", "GC" 等
        :param factor: .update() と .level を持つ因子インスタンス
        """
        if group == "GLOBAL_M":
            self._global_market_factors.append(factor)
        elif group == "GLOBAL_C":
            self._global_capital_factors.append(factor)
        else:
            self._symbol_factors.setdefault(group, []).append(factor)

    async def update_all(
        self,
        signal_bundle: Optional[SignalBundle] = None,
    ) -> None:
        """
        登録された全因子を一括更新する。サブスクリプション時は pulse の先頭で呼ぶ。

        signal_bundle を渡すと Layer 2 の出力を各因子に配布して更新する。
        未渡しの場合は各因子の update() を呼ぶ。
        定義書「4-2 情報の階層構造」参照。
        """
        if signal_bundle is not None:
            await self._update_all_from_signals(signal_bundle)
            return
        all_factors = (
            self._global_market_factors
            + self._global_capital_factors
            + [f for factors in self._symbol_factors.values() for f in factors]
        )
        if all_factors:
            await asyncio.gather(*(f.update() for f in all_factors))

    async def _update_all_from_signals(self, bundle: SignalBundle) -> None:
        """SignalBundle を各因子に配布し、update_from_* を呼ぶ。Layer 3 は Layer 2 出力のみを入力とする。"""
        from .Instruments.c_factor import CFactor
        from .Instruments.p_factor import PFactor
        from .Instruments.r_factor import RFactor
        from .Instruments.s_factor import SFactor
        from .Instruments.t_factor import TFactor
        from .Instruments.u_factor import UFactor
        from .Instruments.v_factor import VFactor

        tasks = []

        for symbol, factors in self._symbol_factors.items():
            price = bundle.price_signals.get(symbol)
            vol = bundle.volatility_signals.get(symbol)
            for f in factors:
                if isinstance(f, PFactor) and price is not None:
                    tasks.append(f.update_from_price_signals(price))
                elif isinstance(f, VFactor) and vol is not None:
                    tasks.append(f.update_from_volatility_signal(vol))
                elif isinstance(f, TFactor) and price is not None:
                    tasks.append(
                        f.apply_trend(
                            price.trend,
                            daily_history=getattr(price, "daily_history", ()),
                        )
                    )
                elif isinstance(f, CFactor) and bundle.liquidity_credit is not None:
                    lc = bundle.liquidity_credit
                    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
                    tasks.append(
                        f.update_from_signals(
                            altitude=lc.altitude,
                            below_sma20=lc.below_sma20 is True,
                            daily_change=lc.daily_change if lc.daily_change is not None else 0.0,
                            daily_history_credit=getattr(lc, "daily_history_credit", ()),
                            below_sma20_lqd=lc_lqd.below_sma20 if lc_lqd is not None else None,
                            daily_change_lqd=lc_lqd.daily_change if lc_lqd and lc_lqd.daily_change is not None else None,
                            daily_history_credit_lqd=getattr(lc_lqd, "daily_history_credit", ()) if lc_lqd else (),
                        )
                    )
                elif isinstance(f, RFactor) and bundle.liquidity_tip is not None:
                    lt = bundle.liquidity_tip
                    tasks.append(
                        f.update_from_signals(
                            altitude=lt.altitude,
                            tip_drawdown_from_high=lt.tip_drawdown_from_high if lt.tip_drawdown_from_high is not None else -0.001,
                            daily_history_tip=getattr(lt, "daily_history_tip", ()),
                        )
                    )
                else:
                    tasks.append(f.update())

        for f in self._global_market_factors:
            tasks.append(f.update())

        cap = bundle.capital_signals
        for f in self._global_capital_factors:
            if cap is not None:
                if isinstance(f, UFactor):
                    tasks.append(f.update_from_ratio(cap.mm_over_nlv))
                elif isinstance(f, SFactor):
                    tasks.append(f.update_from_ratio(cap.span_ratio))
                else:
                    tasks.append(f.update())
            else:
                tasks.append(f.update())

        if tasks:
            await asyncio.gather(*tasks)

    async def get_individual_control_level(self, symbol: str) -> int:
        """
        個別制御層 = max(P, V, C, R) を銘柄 symbol について返す。

        T は含めない（同期制御層用）。C は NQ 系・R は GC 系で銘柄別に登録。定義書「4-2-1 個別制御層」参照。
        """
        from .Instruments.c_factor import CFactor
        from .Instruments.p_factor import PFactor
        from .Instruments.r_factor import RFactor
        from .Instruments.v_factor import VFactor
        relevant = [
            f
            for f in (self._global_market_factors + self._symbol_factors.get(symbol, []))
            if isinstance(f, (PFactor, VFactor, CFactor, RFactor))
        ]
        if not relevant:
            return 0
        return max(f.level for f in relevant)

    async def get_synchronous_control_level(self) -> int:
        """
        同期制御層 = T 相関。

        両銘柄 Downtrend(T=2)→2, 片方→1, 両方 Uptrend/Flat→0。銘柄1つの場合はその T の level。
        定義書「4-2-2 同期制御層」参照。
        """
        if not self._symbol_factors:
            return 0
        from .Instruments.t_factor import TFactor
        t_levels: List[int] = []
        for factors in self._symbol_factors.values():
            for f in factors:
                if isinstance(f, TFactor):
                    t_levels.append(f.level)
                    break
        if not t_levels:
            return 0
        if len(t_levels) == 1:
            return t_levels[0]
        if all(lv == 2 for lv in t_levels):
            return 2
        if any(lv == 2 for lv in t_levels):
            return 1
        return 0

    async def get_limit_control_level(self) -> int:
        """
        制限制御層 = max(U, S)。全エンジン共通。global_capital_factors の最大値。
        定義書「4-2-3 制限制御層」参照。
        """
        if not self._global_capital_factors:
            return 0
        return max(f.level for f in self._global_capital_factors)

    async def get_effective_level(self, symbol: str) -> int:
        """
        実行レベル = max(個別制御層(symbol), 同期制御層, 制限制御層)。定義書「4-2 情報の階層構造」参照。
        """
        ind = await self.get_individual_control_level(symbol)
        syn = await self.get_synchronous_control_level()
        lim = await self.get_limit_control_level()
        return max(ind, syn, lim)

    async def get_throttle_mode(self, symbol: str) -> ModeType:
        """
        実行レベルからスロットルモード（Boost / Cruise / Emergency）を返す。
        定義書「4-2 Effective Level × スロットルモード対応表」。FlightController は判定せずこの戻り値をそのまま適用する。
        """
        effective = await self.get_effective_level(symbol)
        if effective == 0:
            return BOOST
        if effective == 1:
            return CRUISE
        return EMERGENCY

    def _build_reason(self, ind: int, syn: int, lim: int) -> str:
        """
        個別・同期・制限の三層レベルから判定理由文字列を組み立てる。通知用。
        定義書「Phase 5 通知」参照。
        """
        parts: List[str] = []
        if lim > 0:
            parts.append(f"制限層(LCL)={lim}")
        if syn > 0:
            parts.append(f"同期層(SCL)={syn}")
        if ind > 0:
            parts.append(f"個別層(ICL)={ind}")
        return " / ".join(parts) if parts else "全層0"

    async def _get_raw_metrics(self, symbol: str) -> Dict[str, Any]:
        """
        P, V, C, R, T, U, S の現在レベルを収集する。通知用。定義書「Phase 5 raw_metrics」参照。
        """
        metrics: Dict[str, int] = {"P": 0, "V": 0, "C": 0, "R": 0, "T": 0, "U": 0, "S": 0}
        sym_factors = self._symbol_factors.get(symbol, [])
        for f in self._global_market_factors + self._global_capital_factors + sym_factors:
            name = getattr(f, "name", None)
            if name in metrics and hasattr(f, "level"):
                metrics[name] = max(metrics[name], f.level)
        return metrics

    def _get_recovery_metrics(self, symbol: str, bundle: Optional[SignalBundle] = None) -> Dict[str, str]:
        """
        復帰ヒステリシス中の因子について「x/N日目」を収集する。Daily Report 用。
        bundle を渡すとステートレス因子は get_recovery_progress_from_bundle でその場計算。未渡しなら recovery_confirm_progress（U/S 用）。
        """
        result: Dict[str, str] = {}
        sym_factors = self._symbol_factors.get(symbol, [])
        for f in self._global_market_factors + self._global_capital_factors + sym_factors:
            name = getattr(f, "name", None)
            if name is None or name not in ("P", "V", "C", "R", "T", "U", "S"):
                continue
            p = None
            if bundle is not None:
                from_bundle = getattr(f, "get_recovery_progress_from_bundle", None)
                if callable(from_bundle):
                    p = from_bundle(symbol, bundle)
            if p is None:
                prog = getattr(f, "recovery_confirm_progress", None)
                if callable(prog):
                    p = prog()
            if p is not None:
                result[name] = f"{p[0]}/{p[1]}"
        return result

    async def get_flight_controller_signal(self, symbol: str, bundle: Optional[SignalBundle] = None) -> FlightControllerSignal:
        """
        指定銘柄の「計器の結論」を FlightControllerSignal として返す。
        Cockpit の on_flight_controller_signal へ渡す入力。定義書「Phase 5 Signal」参照。
        """
        ind = await self.get_individual_control_level(symbol)
        syn = await self.get_synchronous_control_level()
        lim = await self.get_limit_control_level()
        effective = max(ind, syn, lim)
        reason = self._build_reason(ind, syn, lim)
        is_critical = lim >= 2
        raw_metrics = await self._get_raw_metrics(symbol)
        recovery_metrics = self._get_recovery_metrics(symbol, bundle)
        return FlightControllerSignal(
            throttle_level=effective,
            reason=reason,
            is_critical=is_critical,
            raw_metrics=raw_metrics,
            recovery_metrics=recovery_metrics,
        )
