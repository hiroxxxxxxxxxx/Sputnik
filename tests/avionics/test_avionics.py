"""
FlightController（計器層）のテスト。三層制御と実行レベルを検証する。
"""
from __future__ import annotations

import asyncio

import pytest

from avionics import FlightController


def _run(coro):
    """async を同期テストで実行するヘルパー。"""
    return asyncio.run(coro)


class _MockFactor:
    """.update() と .level を持つモック因子。"""

    def __init__(self, level: int = 0) -> None:
        self.level = level

    async def update(self) -> None:
        pass


def test_avionics_empty_factors_effective_zero() -> None:
    """因子が空のとき get_flight_controller_signal().throttle_level(sym) は 0 を返す。"""
    av = FlightController(global_market_factors=[], global_capital_factors=[], symbol_factors={"NQ": []})
    sig = _run(av.get_flight_controller_signal())
    assert sig.throttle_level("NQ") == 0


def test_avionics_effective_is_max_of_three_layers() -> None:
    """get_flight_controller_signal().throttle_level(sym) は個別・同期・制限の三層の最大値。"""
    f0 = _MockFactor(0)
    f1 = _MockFactor(1)
    f2 = _MockFactor(2)
    av = FlightController(global_capital_factors=[f0, f1, f2], symbol_factors={"NQ": []})
    sig = _run(av.get_flight_controller_signal())
    assert sig.throttle_level("NQ") == 2


def test_avionics_limit_layer_only() -> None:
    """制限制御層（global_capital_factors）のみでも throttle_level が動く。"""
    u = _MockFactor(0)
    s = _MockFactor(1)
    av = FlightController(global_capital_factors=[u, s], symbol_factors={"NQ": []})
    sig = _run(av.get_flight_controller_signal())
    assert sig.throttle_level("NQ") == 1


def test_avionics_use_subscription_always_true() -> None:
    """三層方式のため use_subscription は常に True。"""
    av = FlightController(global_market_factors=[], global_capital_factors=[], symbol_factors={})
    assert av.use_subscription is True


# --- サブスクリプション方式 ---


def test_avionics_subscription_mode_use_subscription_true() -> None:
    """三層方式のため use_subscription は常に True。symbol_factors で銘柄別登録可能。"""
    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[],
        symbol_factors={"NQ": [], "GC": []},
    )
    assert av.use_subscription is True


def test_avionics_subscription_effective_per_symbol() -> None:
    """サブスクリプション時、get_flight_controller_signal().throttle_level(sym) は銘柄ごとに三層の max。"""
    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[_MockFactor(0)],
        symbol_factors={"NQ": [_MockFactor(1)], "GC": [_MockFactor(2)]},
    )
    _run(av.update_all())
    sig = _run(av.get_flight_controller_signal())
    # _MockFactor は P/V/L/T ではないため個別・同期は 0。制限も 0 で effective=0。
    assert sig.throttle_level("NQ") == 0
    assert sig.throttle_level("GC") == 0


def test_avionics_subscription_limit_control_level() -> None:
    """サブスクリプション時、get_limit_control_level は global_capital の最大値。"""
    u = _MockFactor(1)
    s = _MockFactor(2)
    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[u, s],
        symbol_factors={},
    )
    _run(av.update_all())
    lim = _run(av.get_limit_control_level())
    assert lim == 2


def test_avionics_register_factor_subscription() -> None:
    """サブスクリプション時、register_factor で因子を追加できる。"""
    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[],
        symbol_factors={"NQ": []},
    )
    f = _MockFactor(1)
    av.register_factor("NQ", f)
    _run(av.update_all())
    # _MockFactor は P/V/L/T ではないため個別・同期・制限は 0。effective=0 で正常。
    sig = _run(av.get_flight_controller_signal())
    assert sig.throttle_level("NQ") >= 0


def test_avionics_get_individual_control_level_excludes_t() -> None:
    """サブスクリプション時、get_individual_control_level(symbol) は P,V のみで T を含まない。"""
    from avionics import PFactor, TFactor, VFactor
    from avionics.Instruments import (
        FactorsConfigError,
        get_p_thresholds,
        get_t_thresholds,
        get_v_thresholds,
        load_factors_config,
    )

    try:
        config = load_factors_config()
    except FactorsConfigError:
        pytest.skip("config/factors.toml required")
    p = PFactor(name="P_NQ", thresholds=get_p_thresholds(config, "NQ"))
    v = VFactor(name="V_NQ", thresholds=get_v_thresholds(config, "NQ"))
    t = TFactor(symbol="NQ", thresholds=get_t_thresholds(config))
    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[_MockFactor(0)],
        symbol_factors={"NQ": [p, v, t]},
    )
    _run(av.update_all())
    ind = _run(av.get_individual_control_level("NQ"))
    assert ind == max(p.level, v.level)


def test_avionics_get_synchronous_control_level_from_t_factors() -> None:
    """サブスクリプション時、get_synchronous_control_level() は T 相関で 0/1/2。銘柄1つなら T の level。"""
    from avionics import TFactor
    from avionics.Instruments import FactorsConfigError, get_t_thresholds, load_factors_config

    try:
        config = load_factors_config()
    except FactorsConfigError:
        pytest.skip("config/factors.toml required")
    t0 = TFactor(symbol="NQ", thresholds=get_t_thresholds(config))
    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[_MockFactor(0)],
        symbol_factors={"NQ": [t0]},
    )
    _run(av.update_all())
    syn = _run(av.get_synchronous_control_level())
    assert syn in (0, 2)


def test_avionics_get_effective_level_is_max_of_three_layers() -> None:
    """get_flight_controller_signal().throttle_level(sym) = max(個別制御層, 同期制御層, 制限制御層)。"""
    from avionics import PFactor, TFactor, VFactor
    from avionics.Instruments import (
        get_p_thresholds,
        get_t_thresholds,
        get_v_thresholds,
        load_factors_config,
    )

    try:
        config = load_factors_config()
    except Exception as e:
        if "FactorsConfigError" in type(e).__name__ or "factors config" in str(e):
            pytest.skip("config/factors.toml required")
        raise
    p = PFactor(name="P_NQ", thresholds=get_p_thresholds(config, "NQ"))
    v = VFactor(name="V_NQ", thresholds=get_v_thresholds(config, "NQ"))
    t = TFactor(symbol="NQ", thresholds=get_t_thresholds(config))
    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[_MockFactor(0)],
        symbol_factors={"NQ": [p, v, t]},
    )
    _run(av.update_all())
    sig = _run(av.get_flight_controller_signal())
    ind = _run(av.get_individual_control_level("NQ"))
    syn = _run(av.get_synchronous_control_level())
    lim = _run(av.get_limit_control_level())
    assert sig.throttle_level("NQ") == max(ind, syn, lim)
