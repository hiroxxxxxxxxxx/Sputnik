"""
ブループリント（LayerBlueprint）のテスト。
from_dict / from_toml_dict、get_ratios、検証、load_layer_blueprint_from_toml_path をカバー。定義書「0-1-Ⅵ」参照。
"""

from __future__ import annotations

import builtins
import sys
import types
from unittest.mock import patch

import pytest

from engines.blueprint import (
    LayerBlueprint,
    ModeType,
    RATIO_KEYS,
    load_layer_blueprint_from_toml_path,
)


def test_layer_blueprint_from_dict_get_ratios() -> None:
    """from_dict で生成し、get_ratios がモード別に返す。"""
    matrix = {
        "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Emergency": {"future": 1.0, "option_k1": -1.0, "option_k2": 1.0},
    }
    bp = LayerBlueprint.from_dict("Main", matrix)
    assert bp.name == "Main"
    assert bp.get_ratios("Cruise")["future"] == 1.0
    assert bp.get_ratios("Emergency")["option_k2"] == 1.0


def test_layer_blueprint_missing_emergency_raises() -> None:
    """Emergency が無い matrix は ValueError。"""
    matrix = {
        "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
    }
    with pytest.raises(ValueError, match="Emergency"):
        LayerBlueprint.from_dict("X", matrix)


def test_layer_blueprint_missing_ratio_key_raises() -> None:
    """いずれかのモードで option_k2 が欠けていると ValueError。"""
    matrix = {
        "Boost": {"future": 1.0, "option_k1": -1.0},  # option_k2 欠け
        "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Emergency": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
    }
    with pytest.raises(ValueError, match="option_k2"):
        LayerBlueprint.from_dict("X", matrix)


def test_layer_blueprint_from_toml_dict() -> None:
    """from_toml_dict で TOML 由来の辞書から生成できる。"""
    data = {
        "ratios": {
            "Boost": {"future": 1.5, "option_k1": -1.5, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        }
    }
    bp = LayerBlueprint.from_toml_dict("Booster", data)
    assert bp.name == "Booster"
    assert bp.get_ratios("Boost")["future"] == 1.5


def test_layer_blueprint_frozen() -> None:
    """frozen のため代入でエラー。"""
    matrix = {
        "Boost": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        "Cruise": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
    }
    bp = LayerBlueprint.from_dict("X", matrix)
    with pytest.raises(Exception):
        setattr(bp, "name", "Y")


def test_ratio_keys_constant() -> None:
    """RATIO_KEYS は future, option_k1, option_k2。"""
    assert RATIO_KEYS == ("future", "option_k1", "option_k2")


def test_from_toml_dict_ratios_not_dict_raises() -> None:
    """from_toml_dict で ratios が辞書でないと ValueError。"""
    with pytest.raises(ValueError, match="ratios"):
        LayerBlueprint.from_toml_dict("X", {"ratios": "not a dict"})


def test_from_toml_dict_requires_ratios_key() -> None:
    """from_toml_dict で data に ratios キーが無いと ValueError。"""
    data = {
        "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        "Emergency": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
    }
    with pytest.raises(ValueError, match="ratios"):
        LayerBlueprint.from_toml_dict("Main", data)


def test_from_toml_dict_missing_mode_raises() -> None:
    """from_toml_dict で全モードが無いと ValueError。"""
    data = {
        "ratios": {
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        }
    }
    with pytest.raises(ValueError, match="Boost"):
        LayerBlueprint.from_toml_dict("X", data)


def test_from_toml_dict_missing_emergency_raises() -> None:
    """from_toml_dict で Emergency が無いと ValueError。"""
    data = {
        "ratios": {
            "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
        }
    }
    with pytest.raises(ValueError, match="Emergency"):
        LayerBlueprint.from_toml_dict("X", data)


def test_load_layer_blueprint_from_toml_path() -> None:
    """TOML ファイルパスから LayerBlueprint をロードできる。"""
    bp = load_layer_blueprint_from_toml_path("Main", "config/blueprints/main_layer.toml")
    assert bp.name == "Main"
    assert bp.get_ratios("Emergency")["option_k2"] == 1.0


def test_load_layer_blueprint_from_toml_path_fallback_tomli() -> None:
    """tomllib が無い環境では tomli にフォールバックする（except ブロック・127行をカバー）。"""
    real_import = builtins.__import__
    tomli_mock = types.ModuleType("tomli")
    tomli_mock.load = lambda f: {
        "ratios": {
            "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        }
    }

    def import_mock(name: str, *args: object, **kwargs: object):
        if name == "tomllib":
            raise ImportError("no tomllib")
        if name == "tomli":
            return tomli_mock
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=import_mock), patch.dict(
        sys.modules, {"tomli": tomli_mock}
    ):
        bp = load_layer_blueprint_from_toml_path(
            "Main", "config/blueprints/main_layer.toml"
        )
        assert bp.name == "Main"
        assert bp.get_ratios("Emergency")["future"] == 0.0
        # import_mock のフォールバック（real_import）をカバーするため、別モジュールを import
        import os as _os
        assert _os.path is not None
