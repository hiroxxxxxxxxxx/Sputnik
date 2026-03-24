"""
calculate_net_targets のテスト。

合算と base_unit 乗算・丸めを検証。定義書「1-4」「6-2」参照。
"""

from __future__ import annotations

import pytest

from engines.blueprint import LayerBlueprint
from engines.engine import calculate_net_targets


def _make_main_blueprint() -> LayerBlueprint:
    matrix = {
        "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Emergency": {"future": 1.0, "option_k1": -1.0, "option_k2": 1.0},
    }
    return LayerBlueprint.from_dict("Main", matrix)


def _make_booster_blueprint() -> LayerBlueprint:
    matrix = {
        "Boost": {"future": 1.5, "option_k1": -1.5, "option_k2": 0.0},
        "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
    }
    return LayerBlueprint.from_dict("Booster", matrix)


def test_calculate_net_targets_single_layer() -> None:
    """単一層で base_unit 倍して丸められる。"""
    t = calculate_net_targets({"Main": _make_main_blueprint()}, "Cruise", base_unit=2.0)
    assert t["future"] == 2
    assert t["k1"] == -2
    assert t["k2"] == 0


def test_calculate_net_targets_two_layers_aggregate() -> None:
    """複数層を合算する。Boost 時は Main + Booster の比率が足される。"""
    blueprints = {"Main": _make_main_blueprint(), "Booster": _make_booster_blueprint()}
    t = calculate_net_targets(blueprints, "Boost", base_unit=1.0)
    assert t["future"] == round(1.0 + 1.5)
    assert t["k1"] == round(-1.0 + -1.5)
    assert t["k2"] == 0


def test_calculate_net_targets_emergency_booster_zero() -> None:
    """Emergency 時は Booster が 0 なので Main 分のみ。"""
    blueprints = {"Main": _make_main_blueprint(), "Booster": _make_booster_blueprint()}
    t = calculate_net_targets(blueprints, "Emergency", base_unit=2.0)
    assert t["future"] == 2
    assert t["k1"] == -2
    assert t["k2"] == 2
