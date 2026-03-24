"""Engine の calculate_deltas / contract_symbol_for / contract_size_for テスト。"""
from __future__ import annotations

import pytest

from engines.blueprint import LayerBlueprint
from engines.factory import _default_blueprints, build_nq_engine


_CFG = {"base_unit": 1.0, "boost_ratio": 1.0}


@pytest.fixture
def engine():
    return build_nq_engine(blueprints=_default_blueprints(), config=_CFG)


# --- Main layer ---


def test_main_blueprint_and_contract(engine) -> None:
    assert engine.blueprints["Main"].name == "Main"
    assert engine.contract_symbol_for("Main") == "NQ"
    assert engine.contract_size_for("Main") == 1.0


def test_main_calculate_deltas(engine) -> None:
    target = {"future": 1.0, "k1": -1.0, "k2": 0.0}
    deltas = engine.calculate_deltas("Main", target=target, actual=None)
    assert len(deltas) == 2
    assert {d.leg for d in deltas} == {"future", "k1"}
    for d in deltas:
        assert "Main" in d.detail


def test_main_calculate_deltas_with_actual(engine) -> None:
    target = {"future": 2.0, "k1": -1.0, "k2": 0.0}
    actual = {"future": 1.0, "k1": -1.0, "k2": 0.0}
    deltas = engine.calculate_deltas("Main", target=target, actual=actual)
    assert len(deltas) == 1 and deltas[0].leg == "future" and deltas[0].qty == 1.0


# --- Attitude layer ---


def test_attitude_blueprint_and_contract(engine) -> None:
    assert engine.blueprints["Attitude"].name == "Attitude"
    assert engine.contract_symbol_for("Attitude") == "MNQ"
    assert engine.contract_size_for("Attitude") == 0.1


# --- Booster layer ---


def test_booster_blueprint_and_contract(engine) -> None:
    assert engine.blueprints["Booster"].name == "Booster"
    assert engine.contract_symbol_for("Booster") == "MNQ"
    assert engine.contract_size_for("Booster") == 0.1


def test_booster_calculate_deltas(engine) -> None:
    target = {"future": 1.5, "k1": -1.5, "k2": 0.0}
    deltas = engine.calculate_deltas("Booster", target=target, actual=None)
    assert all("Booster" in d.detail for d in deltas)
