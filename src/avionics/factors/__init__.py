"""
フライトコントローラー層：因子（Factors）・シグナル・生データ・設定の実装。

FlightController が参照する個別・同期・制限制御の算出はここで定義する。
定義書「3.フライトコントローラー」「4-2」参照。
"""

from __future__ import annotations

from . import factors_config
from .base_factor import BaseFactor
from .factors_config import (
    FactorsConfigError,
    get_c_thresholds,
    get_p_thresholds,
    get_r_thresholds,
    get_s_thresholds,
    get_t_thresholds,
    get_u_thresholds,
    get_v_thresholds,
    load_factors_config,
)
from .c_factor import CFactor
from .p_factor import PFactor
from .r_factor import RFactor
from .s_factor import SFactor
from .t_factor import TFactor
from .u_factor import UFactor
from .v_factor import VFactor

__all__ = [
    "BaseFactor",
    "CFactor",
    "FactorsConfigError",
    "PFactor",
    "RFactor",
    "SFactor",
    "TFactor",
    "UFactor",
    "VFactor",
    "get_c_thresholds",
    "get_p_thresholds",
    "get_r_thresholds",
    "get_s_thresholds",
    "get_t_thresholds",
    "get_u_thresholds",
    "get_v_thresholds",
    "load_factors_config",
]
