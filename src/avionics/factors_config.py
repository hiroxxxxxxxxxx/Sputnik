"""
後方互換: avionics.factors_config の re-export。実体は avionics.Instruments.factors_config。
"""

from avionics.Instruments.factors_config import (
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

__all__ = [
    "FactorsConfigError",
    "get_c_thresholds",
    "get_p_thresholds",
    "get_r_thresholds",
    "get_s_thresholds",
    "get_t_thresholds",
    "get_u_thresholds",
    "get_v_thresholds",
    "load_factors_config",
]
