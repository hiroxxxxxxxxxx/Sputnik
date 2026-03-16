"""
FlightController の組み立て。

因子と config（factors.toml）から FlightController を組み立てる責務はここに集約する。
scripts（telegram_cockpit_bot, run_cockpit_with_ib）やテストは build_flight_controller を呼ぶだけにする。
"""

from __future__ import annotations

from .data.fc_signals import EngineFactorMapping
from .flight_controller import FlightController
from .Instruments import (
    CFactor,
    PFactor,
    RFactor,
    SFactor,
    TFactor,
    UFactor,
    VFactor,
)
from .Instruments.factors_config import (
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
    設定がない銘柄・因子はスキップし、空の因子リストで FC を返す。
    """
    try:
        config = load_factors_config()
    except FactorsConfigError:
        mapping = EngineFactorMapping(
            symbol_factors={s: [] for s in symbols},
            limit_factors=[],
            global_market_factors=[],
        )
        return FlightController(mapping=mapping)

    global_market_factors: list = []
    limit_factors: list = []
    symbol_factors: dict = {s: [] for s in symbols}

    for sym in symbols:
        try:
            p_th = get_p_thresholds(config, sym)
            v_th = get_v_thresholds(config, sym)
            t_th = get_t_thresholds(config)
            symbol_factors[sym].append(PFactor(name="P", thresholds=p_th))
            symbol_factors[sym].append(VFactor(name="V", thresholds=v_th))
            symbol_factors[sym].append(TFactor(symbol=sym, thresholds=t_th))
        except FactorsConfigError:
            pass
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

    try:
        u_th = get_u_thresholds(config)
        s_th = get_s_thresholds(config)
        limit_factors.extend([UFactor(thresholds=u_th), SFactor(thresholds=s_th)])
    except FactorsConfigError:
        pass

    mapping = EngineFactorMapping(
        symbol_factors=symbol_factors,
        limit_factors=limit_factors,
        global_market_factors=global_market_factors,
    )
    return FlightController(mapping=mapping)
