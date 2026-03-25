"""
FlightController の組み立て。

因子と config（factors.toml）から FlightController を組み立てる責務はここに集約する。
scripts（telegram_cockpit_bot, run_cockpit_with_ib）やテストは build_flight_controller を呼ぶだけにする。
"""

from __future__ import annotations

from .data.factor_mapping import EngineFactorMapping
from .bundle_builder import BundleBuildOptions
from .flight_controller import FlightController
from .factors import (
    CFactor,
    PFactor,
    RFactor,
    SFactor,
    TFactor,
    UFactor,
    VFactor,
)
from .factors.factors_config import (
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


def build_flight_controller(symbols: list[str]) -> FlightController:
    """
    config/factors.toml に基づき因子を登録した FlightController を組み立てる。

    P/V/T（銘柄別必須）、U/S（全体必須）の config が欠損している場合は
    FactorsConfigError をそのまま送出する。
    C/R は銘柄によって適用有無が異なるためオプショナル扱い。
    """
    config = load_factors_config()

    v_recovery_params = {s: get_v_thresholds(config, s)["mid"] for s in symbols}
    bundle_build_options = BundleBuildOptions(v_recovery_params=v_recovery_params)

    global_market_factors: list = []
    limit_factors: list = []
    symbol_factors: dict = {s: [] for s in symbols}

    for sym in symbols:
        p_th = get_p_thresholds(config, sym)
        v_th = get_v_thresholds(config, sym)
        t_th = get_t_thresholds(config)
        symbol_factors[sym].append(PFactor(name="P", thresholds=p_th))
        symbol_factors[sym].append(VFactor(name="V", thresholds=v_th))
        symbol_factors[sym].append(TFactor(symbol=sym, thresholds=t_th))
        try:
            c_th = get_c_thresholds(config, sym)
            symbol_factors[sym].append(CFactor(name="C", thresholds=c_th))
        except FactorsConfigError:
            pass
        try:
            r_th = get_r_thresholds(config, sym)
            symbol_factors[sym].append(RFactor(name="R", thresholds=r_th))
        except FactorsConfigError:
            pass

    u_th = get_u_thresholds(config)
    s_th = get_s_thresholds(config)
    limit_factors.extend([UFactor(thresholds=u_th), SFactor(thresholds=s_th)])

    mapping = EngineFactorMapping(
        symbol_factors=symbol_factors,
        limit_factors=limit_factors,
        global_market_factors=global_market_factors,
    )
    return FlightController(mapping=mapping, bundle_build_options=bundle_build_options)
