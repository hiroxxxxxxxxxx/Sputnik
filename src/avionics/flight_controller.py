"""
FlightController（計器層）：三層制御（個別・同期・制限）の算出に特化。レイヤー混合を避ける。

個別制御層(ICL)・同期制御層(SCL)・制限制御層(LCL)を算出し、get_flight_controller_signal().throttle_level(symbol) = max(ICL,SCL,LCL) で実行レベルを返す。
FlightControllerSignal は全銘柄分の「計器の結論」を内包し、Cockpit（管制層）の承認ゲートへ渡す。
DataSource を注入して refresh すると、内部で fetch_raw → build_signal_bundle → apply_all を実行し、最後の bundle を保持する。
定義書「3.フライトコントローラー」「4-2」「0-1-Ⅲ」参照。
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional

from .data.factor_mapping import EngineFactorMapping
from .data.flight_controller_signal import FlightControllerSignal
from .data.raw_types import RawCapitalSnapshot
from .data.signals import SignalBundle
from .bundle_builder import BundleBuildOptions
from .data.data_source import DataSource


class FlightController:
    """
    計器層。個別制御層(ICL)・同期制御層(SCL)・制限制御層(LCL)の三層のみで実行レベルを算出する。

    global_capital_factors（U,S）, symbol_factors（銘柄別 P,V,T,C/R）を登録し、
    get_flight_controller_signal() で全銘柄分の計器結論を返す。銘柄ごとの実行レベルは
    .throttle_level(symbol) = max(ICL, SCL, LCL)。
    定義書「4-2」計器・「0-1-Ⅲ」抽象構造参照。
    """

    def __init__(
        self,
        *,
        mapping: Optional[EngineFactorMapping] = None,
        global_market_factors: Optional[List[Any]] = None,
        global_capital_factors: Optional[List[Any]] = None,
        symbol_factors: Optional[Dict[str, List[Any]]] = None,
        bundle_build_options: Optional[BundleBuildOptions] = None,
    ) -> None:
        """
        計器を初期化する。EngineFactorMapping を渡すか、従来の三リストで渡す。

        :param mapping: エンジン(Symbol)↔Factor のマッピング。Assembly が組み立てたものを渡す。
        :param global_market_factors: mapping 未指定時用。全エンジン共通の個別制御用因子
        :param global_capital_factors: mapping 未指定時用。制限制御層(LCL)因子（U, S）
        :param symbol_factors: mapping 未指定時用。銘柄別因子。{"NQ": [P,V,T,C], "GC": [P,V,T,R]} 等
        :param bundle_build_options: refresh 時に build_signal_bundle へ渡すオプション。未指定時はデフォルトで組み立てる。
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
        self._bundle_build_options = bundle_build_options
        self._last_bundle: Optional[SignalBundle] = None
        self._last_capital_snapshot: Optional[RawCapitalSnapshot] = None

    def register_factor(self, group: str, factor: Any) -> None:
        """
        因子を登録する。マッピングのリストに追加する（組み立て時・テスト用）。

        :param group: "GLOBAL_M"（L）, "GLOBAL_C"（U,S）, "NQ", "GC" 等
        :param factor: .apply_signal_bundle() と .level を持つ因子インスタンス
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

    async def refresh(
        self,
        data_source: DataSource,
        as_of: date,
        symbols: List[str],
    ) -> None:
        """
        DataSource から Raw を取得し、build_signal_bundle → apply_all で最新状態に更新する。
        取得した bundle と capital_snapshot は内部に保持し、get_last_bundle() / get_last_capital_snapshot() で参照できる。
        """
        opts = self._bundle_build_options
        if opts is None:
            raise ValueError("FlightController.refresh requires bundle_build_options")
        raw_snapshot, capital_snapshot = await data_source.fetch_raw(
            as_of,
            symbols,
            volatility_symbols=opts.volatility_symbols,
            liquidity_credit_hyg_symbol=opts.liquidity_credit_hyg_symbol,
            liquidity_credit_lqd_symbol=opts.liquidity_credit_lqd_symbol,
            liquidity_tip_symbol=opts.liquidity_tip_symbol,
            account=opts.account,
            base_density=opts.base_density,
            v_recovery_params=opts.v_recovery_params,
        )
        from .bundle_builder import build_signal_bundle

        bundle = build_signal_bundle(
            raw_snapshot,
            as_of,
            symbols,
            liquidity_credit_hyg_symbol=opts.liquidity_credit_hyg_symbol,
            liquidity_credit_lqd_symbol=opts.liquidity_credit_lqd_symbol,
            liquidity_tip_symbol=opts.liquidity_tip_symbol,
            altitude=opts.altitude,
            v_recovery_params=opts.v_recovery_params,
        )
        self._last_bundle = bundle
        self._last_capital_snapshot = capital_snapshot
        await self.apply_all(bundle)

    def get_last_bundle(self) -> Optional[SignalBundle]:
        """最後に refresh した SignalBundle。未 refresh の場合は None。"""
        return self._last_bundle

    def get_last_capital_snapshot(self) -> Optional[RawCapitalSnapshot]:
        """最後に refresh した RawCapitalSnapshot。未 refresh の場合は None。"""
        return self._last_capital_snapshot

    async def apply_all(self, bundle: SignalBundle) -> None:
        """
        SignalBundle を登録された全因子に配布して更新する。

        各因子の apply_signal_bundle(symbol, bundle) を呼び、因子の level を最新にする。
        定義書「4-2 情報の階層構造」参照。
        """
        tasks = []
        for symbol, factors in self._mapping.symbol_factors.items():
            for f in factors:
                tasks.append(f.apply_signal_bundle(symbol, bundle))
        for f in self._mapping.global_market_factors:
            tasks.append(f.apply_signal_bundle(None, bundle))
        for f in self._mapping.limit_factors:
            tasks.append(f.apply_signal_bundle(None, bundle))
        if tasks:
            await asyncio.gather(*tasks)

    def get_individual_control_level(self, symbol: str) -> int:
        """
        ICL（個別制御層）= max(P, V, C, R) を銘柄 symbol について返す。

        T は含めない（SCL 用）。因子は apply_all 済みである前提。
        定義書「4-2-1 個別制御層」参照。
        """
        from .factors.c_factor import CFactor
        from .factors.p_factor import PFactor
        from .factors.r_factor import RFactor
        from .factors.v_factor import VFactor

        m = self._mapping
        relevant = [
            f
            for f in (m.global_market_factors + m.symbol_factors.get(symbol, []))
            if isinstance(f, (PFactor, VFactor, CFactor, RFactor))
        ]
        if not relevant:
            return 0
        return max(f.level for f in relevant)

    def get_synchronous_control_level(self) -> int:
        """
        SCL（同期制御層）= T 相関。

        両銘柄 Downtrend(T=2)→2, 片方→1, 両方 Uptrend/Flat→0。
        銘柄1つの場合はその T の level。因子は apply_all 済みである前提。
        定義書「4-2-2 同期制御層」参照。
        """
        m = self._mapping
        if not m.symbol_factors:
            return 0
        from .factors.t_factor import TFactor

        t_levels: List[int] = []
        for factors in m.symbol_factors.values():
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

    def get_limit_control_level(self) -> int:
        """
        LCL（制限制御層）= max(U, S)。全エンジン共通。

        因子は apply_all 済みである前提。定義書「4-2-3 制限制御層」参照。
        """
        if not self._mapping.limit_factors:
            return 0
        return max(f.level for f in self._mapping.limit_factors)

    async def get_flight_controller_signal(self) -> FlightControllerSignal:
        """
        全銘柄分の「計器の結論」を 1 つの FlightControllerSignal として返す。
        現在の因子の level から算出する（refresh 済みならその bundle で更新された状態）。
        NQ/GC 固定のフィールドに ICL/SCL/LCL と因子レベル（P,V,C,R,T,U,S）を包含する。
        Cockpit の承認ゲートや Protocol 起動の入力。定義書「Phase 5 Signal」参照。
        """
        def _collect_symbol_metrics(symbol: str) -> Dict[str, int]:
            metrics: Dict[str, int] = {"P": 0, "V": 0, "C": 0, "R": 0, "T": 0}
            sym_factors = self._mapping.symbol_factors.get(symbol, [])
            for f in self._mapping.global_market_factors + sym_factors:
                name = getattr(f, "name", None)
                if not name or not hasattr(f, "level"):
                    continue
                if name in metrics:
                    metrics[name] = max(metrics[name], int(f.level))
                elif isinstance(name, str) and name.startswith("T_"):
                    metrics["T"] = max(metrics["T"], int(f.level))
            return metrics

        def _collect_limit_metrics() -> Dict[str, int]:
            metrics: Dict[str, int] = {"U": 0, "S": 0}
            for f in self._mapping.limit_factors:
                name = getattr(f, "name", None)
                if not name or not hasattr(f, "level"):
                    continue
                if name in metrics:
                    metrics[name] = max(metrics[name], int(f.level))
            return metrics

        scl = self.get_synchronous_control_level()
        lcl = self.get_limit_control_level()

        has_nq = "NQ" in self._mapping.symbol_factors
        has_gc = "GC" in self._mapping.symbol_factors
        nq_icl = self.get_individual_control_level("NQ") if has_nq else 0
        gc_icl = self.get_individual_control_level("GC") if has_gc else 0

        nq_m = _collect_symbol_metrics("NQ") if has_nq else {"P": 0, "V": 0, "C": 0, "R": 0, "T": 0}
        gc_m = _collect_symbol_metrics("GC") if has_gc else {"P": 0, "V": 0, "C": 0, "R": 0, "T": 0}
        lim_m = _collect_limit_metrics()

        t = scl
        u = lim_m.get("U", 0)
        s = lim_m.get("S", 0)

        return FlightControllerSignal(
            scl=scl,
            lcl=lcl,
            nq_icl=nq_icl,
            gc_icl=gc_icl,
            nq_p=nq_m.get("P", 0),
            nq_v=nq_m.get("V", 0),
            nq_c=nq_m.get("C", 0),
            nq_r=nq_m.get("R", 0),
            gc_p=gc_m.get("P", 0),
            gc_v=gc_m.get("V", 0),
            gc_c=gc_m.get("C", 0),
            gc_r=gc_m.get("R", 0),
            t=t,
            u=u,
            s=s,
        )
