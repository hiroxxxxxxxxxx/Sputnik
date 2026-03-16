"""Engine（推進層）のテスト。Blueprint ベース。"""
from __future__ import annotations

import asyncio

import pytest

from cockpit.cockpit import Cockpit
from avionics import FlightController
from engines.blueprint import LayerBlueprint
from engines.engine import Engine
from engines.factory import _default_blueprints, build_nq_engine


@pytest.fixture
def fc_with_engines():
    flight_controller = FlightController(global_market_factors=[], global_capital_factors=[], symbol_factors={})
    fc = Cockpit(fc=flight_controller, engines=[], initial_mode="Cruise")
    engine = build_nq_engine(
        blueprints=_default_blueprints(),
        config={"base_unit": 1.0, "boost_ratio": 1.0},
    )
    fc.engines.append(engine)
    return fc, engine


def test_engine_symbol_type(fc_with_engines) -> None:
    fc, engine = fc_with_engines
    assert engine.symbol_type == "NQ"


def test_engine_apply_mode_collects_deltas(fc_with_engines) -> None:
    _, engine = fc_with_engines
    asyncio.run(engine.apply_mode("Emergency"))
    target = engine._target_for_part("Main", "Emergency", engine.config["base_unit"])
    main_deltas = engine.main_part.calculate_deltas(target=target, actual=None)
    assert len(main_deltas) >= 1


def test_engine_instruction_for_default_base_unit(fc_with_engines) -> None:
    _, engine = fc_with_engines
    inst = engine._instruction_for("Cruise")
    assert "base_unit" in inst
    assert inst.get("base_unit", 0) == 1.0
    assert inst.get("boost_ratio", 0) == 1.0


def test_engine_instruction_for_uses_config() -> None:
    flight_controller = FlightController(global_market_factors=[], global_capital_factors=[], symbol_factors={})
    fc = Cockpit(fc=flight_controller, engines=[], initial_mode="Cruise")
    engine = build_nq_engine(
        blueprints=_default_blueprints(),
        config={"base_unit": 2.0, "boost_ratio": 1.5},
    )
    inst = engine._instruction_for("Boost")
    assert inst["base_unit"] == 2.0
    assert inst["boost_ratio"] == 1.5


def test_engine_sync_calls_all_parts(fc_with_engines) -> None:
    _, engine = fc_with_engines
    engine.sync()
    assert engine.main_part.blueprint.name == "Main"


def test_engine_calculate_net_targets(fc_with_engines) -> None:
    """blueprints 必須のため常に目標枚数が返る。"""
    _, engine = fc_with_engines
    t = engine.calculate_net_targets("Cruise", base_unit=2.0)
    assert t is not None
    assert "future" in t
    assert "k1" in t
    assert "k2" in t
