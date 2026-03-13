"""
フライトコントローラー層：因子（Factors）・シグナル・生データ・設定の実装。

FlightController が参照する個別・同期・制限制御の算出はここで定義する。
定義書「3.フライトコントローラー」「4-2」参照。
"""

from __future__ import annotations

# サブモジュールをパッケージから参照できるようにする
from . import factors_config
from . import raw_data
from . import signals

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
from .raw_data import PriceBar, PriceBar1h, RawCapitalSnapshot, RawDataProvider
from .s_factor import SFactor
from .signals import (
    CapitalSignals,
    LiquiditySignals,
    PriceSignals,
    SignalBundle,
    VolatilitySignal,
)
from .t_factor import TFactor
from .u_factor import UFactor
from .v_factor import VFactor

__all__ = [
    "BaseFactor",
    "CapitalSignals",
    "CFactor",
    "FactorsConfigError",
    "LiquiditySignals",
    "PFactor",
    "PriceBar",
    "PriceBar1h",
    "PriceSignals",
    "RawCapitalSnapshot",
    "RFactor",
    "RawDataProvider",
    "SFactor",
    "SignalBundle",
    "TFactor",
    "UFactor",
    "VFactor",
    "VolatilitySignal",
    "get_c_thresholds",
    "get_p_thresholds",
    "get_r_thresholds",
    "get_s_thresholds",
    "get_t_thresholds",
    "get_u_thresholds",
    "get_v_thresholds",
    "load_factors_config",
]
