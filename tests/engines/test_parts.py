"""MainPart / AttitudePart / BoosterPart。Part は FC を参照せず、目標と現在の差分のみ算出。"""
from __future__ import annotations

import pytest

from engines.blueprint import LayerBlueprint
from engines.main_part import MainPart
from engines.attitude_part import AttitudePart
from engines.booster_part import BoosterPart


def _main_bp() -> LayerBlueprint:
    return LayerBlueprint.from_dict(
        "Main",
        {
            "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 1.0, "option_k1": -1.0, "option_k2": 1.0},
        },
    )


def _attitude_bp() -> LayerBlueprint:
    return LayerBlueprint.from_dict(
        "Attitude",
        {
            "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        },
    )


def _booster_bp() -> LayerBlueprint:
    return LayerBlueprint.from_dict(
        "Booster",
        {
            "Boost": {"future": 1.5, "option_k1": -1.5, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        },
    )


@pytest.fixture
def main_part() -> MainPart:
    return MainPart(_main_bp(), "NQ")


@pytest.fixture
def attitude_part() -> AttitudePart:
    return AttitudePart(_attitude_bp(), "NQ")


@pytest.fixture
def booster_part() -> BoosterPart:
    return BoosterPart(_booster_bp(), "NQ")


# --- MainPart ---


def test_main_part_blueprint_and_contract(main_part: MainPart) -> None:
    assert main_part.blueprint.name == "Main"
    assert main_part.LAYER_TYPE == "MINI"
    assert main_part.contract_symbol == "NQ"
    assert main_part.contract_size == 1.0


def test_main_part_calculate_deltas(main_part: MainPart) -> None:
    target = {"future": 1.0, "k1": -1.0, "k2": 0.0}
    deltas = main_part.calculate_deltas(target=target, actual=None)
    # k2 は target=0, actual=0 のため差分なしで含まれない
    assert len(deltas) == 2
    assert {d.leg for d in deltas} == {"future", "k1"}
    for d in deltas:
        assert "MainPart" in d.detail


def test_main_part_calculate_deltas_with_actual(main_part: MainPart) -> None:
    target = {"future": 2.0, "k1": -1.0, "k2": 0.0}
    actual = {"future": 1.0, "k1": -1.0, "k2": 0.0}
    deltas = main_part.calculate_deltas(target=target, actual=actual)
    assert len(deltas) == 1 and deltas[0].leg == "future" and deltas[0].qty == 1.0


# --- AttitudePart ---


def test_attitude_part_blueprint_and_contract(attitude_part: AttitudePart) -> None:
    assert attitude_part.blueprint.name == "Attitude"
    assert attitude_part.LAYER_TYPE == "MICRO"
    assert attitude_part.contract_symbol == "MNQ"
    assert attitude_part.contract_size == 0.1


# --- BoosterPart ---


def test_booster_part_blueprint_and_contract(booster_part: BoosterPart) -> None:
    assert booster_part.blueprint.name == "Booster"
    assert booster_part.contract_symbol == "MNQ"
    assert booster_part.contract_size == 0.1


def test_booster_part_calculate_deltas(booster_part: BoosterPart) -> None:
    target = {"future": 1.5, "k1": -1.5, "k2": 0.0}
    deltas = booster_part.calculate_deltas(target=target, actual=None)
    assert all("BoosterPart" in d.detail for d in deltas)
