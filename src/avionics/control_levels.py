"""
三層制御レベル（ICL / SCL / LCL）の算出に特化したモジュール。

EngineFactorMapping を入力に、apply_all 済みの因子の level を読んで ICL/SCL/LCL を返す。
FlightController は apply_all のあとこのモジュールにマッピングを渡して三層を取得する。
定義書「4-2」個別制御層・同期制御層・制限制御層参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .data.fc_signals import EngineFactorMapping


def compute_icl(mapping: "EngineFactorMapping", symbol: str) -> int:
    """
    ICL（個別制御層）= max(P, V, C, R) を銘柄 symbol について返す。

    T は含めない（SCL 用）。因子は apply_all 済みである前提。
    定義書「4-2-1 個別制御層」参照。
    """
    from .factors.c_factor import CFactor
    from .factors.p_factor import PFactor
    from .factors.r_factor import RFactor
    from .factors.v_factor import VFactor
    relevant = [
        f
        for f in (mapping.global_market_factors + mapping.symbol_factors.get(symbol, []))
        if isinstance(f, (PFactor, VFactor, CFactor, RFactor))
    ]
    if not relevant:
        return 0
    return max(f.level for f in relevant)


def compute_scl(mapping: "EngineFactorMapping") -> int:
    """
    SCL（同期制御層）= T 相関。

    両銘柄 Downtrend(T=2)→2, 片方→1, 両方 Uptrend/Flat→0。銘柄1つの場合はその T の level。
    因子は apply_all 済みである前提。定義書「4-2-2 同期制御層」参照。
    """
    if not mapping.symbol_factors:
        return 0
    from .factors.t_factor import TFactor
    t_levels: List[int] = []
    for factors in mapping.symbol_factors.values():
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


def compute_lcl(mapping: "EngineFactorMapping") -> int:
    """
    LCL（制限制御層）= max(U, S)。全エンジン共通。

    因子は apply_all 済みである前提。定義書「4-2-3 制限制御層」参照。
    """
    if not mapping.limit_factors:
        return 0
    return max(f.level for f in mapping.limit_factors)
