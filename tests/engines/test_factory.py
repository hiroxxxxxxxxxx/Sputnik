"""
Factory（build_nq_engine, build_gc_engine, build_engine_pair）のテスト。
"""
from __future__ import annotations

import pytest

from cockpit.cockpit import Cockpit
from avionics import FlightController
from engines.factory import (
    _default_blueprints,
    build_engine_pair,
    build_gc_engine,
    build_nq_engine,
)


@pytest.fixture
def cockpit():
    """空のエンジンリストで Cockpit（管制）を用意。"""
    fc = FlightController(global_market_factors=[], global_capital_factors=[], symbol_factors={})
    return Cockpit(fc=fc, engines=[], initial_mode="Cruise")


def test_build_nq_engine_returns_engine(cockpit) -> None:
    """build_nq_engine は NQ 用 Engine を1台返す。"""
    engine = build_nq_engine(
        blueprints=_default_blueprints(),
        config={"base_unit": 1.0, "boost_ratio": 1.0},
    )
    assert engine.symbol_type == "NQ"
    assert engine.main_part.blueprint.name == "Main"
    assert engine.main_part.contract_symbol == "NQ"
    assert engine.booster_part.blueprint.name == "Booster"
    assert engine.booster_part.contract_symbol == "MNQ"


def test_build_nq_engine_custom_blueprints(cockpit) -> None:
    """blueprints を渡すとその設計図で組み立てる。"""
    from engines.blueprint import LayerBlueprint
    bp = LayerBlueprint.from_dict(
        "Main",
        {"Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
         "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
         "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0}},
    )
    engine = build_nq_engine(
        blueprints={"Main": bp, "Attitude": bp, "Booster": bp},
        config={"base_unit": 1.0, "boost_ratio": 1.0},
    )
    assert engine.main_part.blueprint is bp


def test_build_gc_engine_returns_engine(cockpit) -> None:
    """build_gc_engine は GC 用 Engine を1台返す。"""
    engine = build_gc_engine(
        blueprints=_default_blueprints(),
        config={"base_unit": 1.0, "boost_ratio": 1.0},
    )
    assert engine.symbol_type == "GC"
    assert engine.main_part.symbol_type == "GC"
    assert engine.booster_part.contract_symbol == "MGC"


def test_build_gc_engine_with_config(cockpit) -> None:
    """build_gc_engine に config を渡せる。"""
    engine = build_gc_engine(
        blueprints=_default_blueprints(),
        config={"base_unit": 1.0, "boost_ratio": 1.5},
    )
    assert engine.config.get("boost_ratio") == 1.5


def test_build_engine_pair_returns_nq_and_gc(cockpit) -> None:
    """build_engine_pair は (engine_nq, engine_gc) を返す。"""
    bp = _default_blueprints()
    cfg = {"base_unit": 1.0, "boost_ratio": 1.0}
    nq, gc = build_engine_pair(
        blueprints_nq=bp,
        blueprints_gc=bp,
        nq_config=cfg,
        gc_config=cfg,
    )
    assert nq.symbol_type == "NQ"
    assert gc.symbol_type == "GC"


def test_build_engine_pair_nq_gc_config(cockpit) -> None:
    """build_engine_pair に nq_config / gc_config を渡せる。"""
    bp = _default_blueprints()
    nq, gc = build_engine_pair(
        blueprints_nq=bp,
        blueprints_gc=bp,
        nq_config={"base_unit": 1.0, "boost_ratio": 2.0},
        gc_config={"base_unit": 1.0, "boost_ratio": 1.2},
    )
    assert nq.config.get("boost_ratio") == 2.0
    assert gc.config.get("boost_ratio") == 1.2


def test_build_engine_pair_same_structure_as_individual(cockpit) -> None:
    """build_engine_pair で作ったエンジンは build_nq/build_gc と同じ構成。"""
    bp = _default_blueprints()
    cfg = {"base_unit": 1.0, "boost_ratio": 1.0}
    nq1 = build_nq_engine(blueprints=bp, config=cfg)
    gc1 = build_gc_engine(blueprints=bp, config=cfg)
    nq2, gc2 = build_engine_pair(
        blueprints_nq=bp, blueprints_gc=bp, nq_config=cfg, gc_config=cfg
    )
    assert nq1.main_part.blueprint.name == nq2.main_part.blueprint.name
    assert gc1.booster_part.blueprint.name == gc2.booster_part.blueprint.name
