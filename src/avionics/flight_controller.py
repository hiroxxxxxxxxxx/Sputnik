"""
FlightController（計器層）：三層制御（個別・同期・制限）の算出に特化。レイヤー混合を避ける。

個別制御層(ICL)・同期制御層(SCL)・制限制御層(LCL)を算出し、get_flight_controller_signal().by_symbol[symbol].throttle_level = max(ICL,SCL,LCL) で実行レベルを返す。
FlightControllerSignal は全銘柄分の「計器の結論」を内包し、Cockpit（管制層）の承認ゲートへ渡す。
定義書「3.フライトコントローラー」「4-2」「0-1-Ⅲ」参照。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .data.fc_signals import EngineFactorMapping, FlightControllerSignal, SymbolSignal
from .data.signals import SignalBundle


class FlightController:
    """
    計器層。個別制御層(ICL)・同期制御層(SCL)・制限制御層(LCL)の三層のみで実行レベルを算出する。

    global_capital_factors（U,S）, symbol_factors（銘柄別 P,V,T,C/R）を登録し、
    get_flight_controller_signal() で全銘柄分の計器結論を返す。銘柄ごとの実行レベルは
    .by_symbol[symbol].throttle_level = max(ICL, SCL, LCL)。
    定義書「4-2」計器・「0-1-Ⅲ」抽象構造参照。
    """

    def __init__(
        self,
        *,
        mapping: Optional[EngineFactorMapping] = None,
        global_market_factors: Optional[List[Any]] = None,
        global_capital_factors: Optional[List[Any]] = None,
        symbol_factors: Optional[Dict[str, List[Any]]] = None,
    ) -> None:
        """
        計器を初期化する。EngineFactorMapping を渡すか、従来の三リストで渡す。

        :param mapping: エンジン(Symbol)↔Factor のマッピング。Assembly が組み立てたものを渡す。
        :param global_market_factors: mapping 未指定時用。全エンジン共通の個別制御用因子
        :param global_capital_factors: mapping 未指定時用。制限制御層(LCL)因子（U, S）
        :param symbol_factors: mapping 未指定時用。銘柄別因子。{"NQ": [P,V,T,C], "GC": [P,V,T,R]} 等
        定義書「4-2」「0-1-Ⅲ」参照。
        """
        if mapping is not None:
            self._mapping = mapping
        else:
            self._mapping = EngineFactorMapping(
                symbol_factors=dict(symbol_factors or {}),
                limit_factors=list(global_capital_factors or []),
                global_market_factors=list(global_market_factors or []),
            )

    @property
    def use_subscription(self) -> bool:
        """三層方式で銘柄別に個別・同期・制限を算出する。常に True。"""
        return True

    def register_factor(self, group: str, factor: Any) -> None:
        """
        因子を登録する。マッピングのリストに追加する（組み立て時・テスト用）。

        :param group: "GLOBAL_M"（L）, "GLOBAL_C"（U,S）, "NQ", "GC" 等
        :param factor: .update() と .level を持つ因子インスタンス
        """
        m = self._mapping
        if group == "GLOBAL_M":
            m.global_market_factors.append(factor)
        elif group == "GLOBAL_C":
            m.limit_factors.append(factor)
        else:
            m.symbol_factors.setdefault(group, []).append(factor)

    @property
    def mapping(self) -> EngineFactorMapping:
        """表示用ヘルパー（raw_metrics / recovery_metrics 等）に渡すマッピング。読み取り専用。"""
        return self._mapping

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
        m = self._mapping
        all_factors = (
            m.global_market_factors
            + m.limit_factors
            + [f for factors in m.symbol_factors.values() for f in factors]
        )
        if all_factors:
            await asyncio.gather(*(f.update() for f in all_factors))

    async def _update_all_from_signals(self, bundle: SignalBundle) -> None:
        """SignalBundle を各因子に渡し、BaseFactor.update_from_signal_bundle で更新する。因子の import は不要。"""
        tasks = []
        for symbol, factors in self._mapping.symbol_factors.items():
            for f in factors:
                tasks.append(f.update_from_signal_bundle(symbol, bundle))
        for f in self._mapping.global_market_factors:
            tasks.append(f.update_from_signal_bundle(None, bundle))
        for f in self._mapping.limit_factors:
            tasks.append(f.update_from_signal_bundle(None, bundle))
        if tasks:
            await asyncio.gather(*tasks)

    async def get_individual_control_level(self, symbol: str) -> int:
        """
        ICL（個別制御層）= max(P, V, C, R) を銘柄 symbol について返す。
        ControlLevels.compute_icl に委譲。定義書「4-2-1 個別制御層」参照。
        """
        from .control_levels import compute_icl
        return compute_icl(self._mapping, symbol)

    async def get_synchronous_control_level(self) -> int:
        """
        SCL（同期制御層）= T 相関。ControlLevels.compute_scl に委譲。
        定義書「4-2-2 同期制御層」参照。
        """
        from .control_levels import compute_scl
        return compute_scl(self._mapping)

    async def get_limit_control_level(self) -> int:
        """
        LCL（制限制御層）= max(U, S)。ControlLevels.compute_lcl に委譲。
        定義書「4-2-3 制限制御層」参照。
        """
        from .control_levels import compute_lcl
        return compute_lcl(self._mapping)

    async def get_flight_controller_signal(self, bundle: Optional[SignalBundle] = None) -> FlightControllerSignal:
        """
        全銘柄分の「計器の結論」を 1 つの FlightControllerSignal として返す。
        by_symbol[symbol] で銘柄ごとの SymbolSignal（throttle_level / icl / is_critical）を参照する。
        表示用（reason / raw_metrics / recovery_metrics）は reports.format_fc_signal ヘルパーから取得。
        Cockpit の承認ゲートや Protocol 起動の入力。定義書「Phase 5 Signal」参照。
        """
        by_symbol: Dict[str, SymbolSignal] = {}
        scl = await self.get_synchronous_control_level()
        lcl = await self.get_limit_control_level()
        for symbol in self._mapping.symbol_factors:
            icl = await self.get_individual_control_level(symbol)
            effective = max(icl, scl, lcl)
            is_critical = lcl >= 2
            by_symbol[symbol] = SymbolSignal(
                throttle_level=effective,
                icl=icl,
                is_critical=is_critical,
            )
        return FlightControllerSignal(by_symbol=by_symbol, scl=scl, lcl=lcl)
