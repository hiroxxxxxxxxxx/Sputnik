"""
ブループリント（設計図）：モード別の比率・戦略を保持する読み取り専用のデータ層。

TOML/JSON のマトリクスデータをロードし、起動時に検証したうえで frozen なデータクラスとして保持する。
実行中の書き換えを防ぎ、定義書「0-1-Ⅵ」の自己改造禁止を体現する。
層タイプ（MINI/MICRO）と発注用 contract_symbol / contract_size もここで定義。
定義書「1-3」「1-4」参照。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Tuple

from cockpit.mode import ModeType, MODES

# 層タイプ（Main=MINI, Attitude/Booster=MICRO）。発注先・重み算出に使用。
LayerType = Literal["MINI", "MICRO"]

PART_NAMES: Tuple[str, ...] = ("Main", "Attitude", "Booster")

PART_LAYER_TYPES: Dict[str, LayerType] = {
    "Main": "MINI",
    "Attitude": "MICRO",
    "Booster": "MICRO",
}


def contract_symbol(symbol_type: Literal["NQ", "GC"], layer_type: LayerType) -> str:
    """
    発注時に使う契約シンボル。Mini→NQ/GC、Micro→MNQ/MGC。
    定義書「1-3」参照。
    """
    if symbol_type == "NQ":
        return "NQ" if layer_type == "MINI" else "MNQ"
    return "GC" if layer_type == "MINI" else "MGC"


def contract_size(layer_type: LayerType) -> float:
    """
    1単位あたりの重み。Mini=1.0、Micro=0.1。発注枚数・デルタ計算に使用。
    定義書「1-3」参照。
    """
    return 1.0 if layer_type == "MINI" else 0.1

# 有効なモード（TOML キーとの対応）。core.mode.MODES を参照。
_MODES: Tuple[ModeType, ...] = MODES
AltitudeKey = Literal["high", "mid", "low"]
ALTITUDES: Tuple[AltitudeKey, ...] = ("high", "mid", "low")

# 比率キー（Inventory が合算に使用）
RATIO_KEYS: Tuple[str, ...] = ("future", "option_k1", "option_k2")


@dataclass(frozen=True)
class LayerBlueprint:
    """
    特定の層（Main / Attitude / Booster）の設計図。

    マトリクスデータを保持し、モードに応じた比率を返す。
    frozen により実行中の変更を禁止。定義書「0-1-Ⅵ」参照。
    """

    name: str
    # frozen のため hashable に: (mode, tuple of (k,v)) の tuple
    _matrix: Tuple[Tuple[ModeType, Tuple[Tuple[str, Any], ...]], ...]

    def __post_init__(self) -> None:
        """起動時に全モード・全比率キーの存在を検証。"""
        d = self._matrix_dict()
        for mode in _MODES:
            if mode not in d:
                raise ValueError(
                    f"LayerBlueprint matrix must contain all modes (Boost, Cruise, Emergency). Missing: {mode!r}."
                )
        for mode, ratios in d.items():
            for key in RATIO_KEYS:
                if key not in ratios:
                    raise ValueError(f"LayerBlueprint matrix[{mode!r}] must have {key!r}.")

    def _matrix_dict(self) -> Dict[ModeType, Dict[str, Any]]:
        """tuple 化された matrix を辞書に復元。"""
        return {mode: dict(pairs) for mode, pairs in self._matrix}

    def get_ratios(self, mode: ModeType) -> Dict[str, Any]:
        """
        指定モードの比率辞書を返す。ロード時に全モードの存在を検証済みのため key は必ず存在する。
        """
        d = self._matrix_dict()
        return dict(d[mode])

    @classmethod
    def from_dict(cls, name: str, matrix: Dict[ModeType, Dict[str, Any]]) -> "LayerBlueprint":
        """
        辞書から LayerBlueprint を生成する。frozen 用に tuple 化して保持。

        :param name: 層の名前（Main / Attitude / Booster）
        :param matrix: モード別比率。各エントリに future, option_k1, option_k2 が必須。
        """
        frozen_matrix = tuple((mode, tuple(ratios.items())) for mode, ratios in matrix.items())
        return cls(name=name, _matrix=frozen_matrix)

    @classmethod
    def from_toml_dict(cls, name: str, data: Dict[str, Any]) -> "LayerBlueprint":
        """
        TOML 由来の辞書から LayerBlueprint を生成する。

        data["ratios"] 必須。Boost / Cruise / Emergency の全キーが必須。
        例: data = {"ratios": {"Boost": {...}, "Cruise": {...}, "Emergency": {...}}}
        """
        if "ratios" not in data:
            raise ValueError("TOML data must have 'ratios' key.")
        ratios = data["ratios"]
        if not isinstance(ratios, dict):
            raise ValueError("TOML data['ratios'] must be a dict.")
        matrix: Dict[ModeType, Dict[str, Any]] = {}
        for mode in _MODES:
            if mode not in ratios:
                raise ValueError(f"TOML ratios must contain all modes. Missing: {mode!r}.")
            matrix[mode] = dict(ratios[mode])
        return cls.from_dict(name=name, matrix=matrix)


def load_layer_blueprint_from_toml_path(name: str, path: str) -> LayerBlueprint:
    """
    TOML ファイルパスから LayerBlueprint を生成する。

    :param name: 層の名前（Main / Attitude / Booster）
    :param path: 単一レイヤー TOML ファイルへのパス。Python 3.11+ は tomllib、それ以前は tomli を使用。
    """
    with open(path, "rb") as f:
        try:
            import tomllib
            data = tomllib.load(f)
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
            data = tomllib.load(f)
    return LayerBlueprint.from_toml_dict(name=name, data=data)


def load_blueprints_from_unified_toml_path(
    path: str, *, altitude: AltitudeKey = "mid"
) -> Dict[str, LayerBlueprint]:
    """
    統合 blueprint TOML（base + part_caps + overrides）から、
    指定高度の全 Part LayerBlueprint を返す。
    """
    mode_part_raw = load_effective_mode_part_config_from_toml_path(path, altitude=altitude)
    out: Dict[str, LayerBlueprint] = {}
    for part_name in PART_NAMES:
        matrix: Dict[ModeType, Dict[str, Any]] = {}
        for mode in _MODES:
            part_payload = {
                k: v
                for k, v in mode_part_raw[mode][part_name].items()
                if k != "legs"
            }
            matrix[mode] = part_payload
        out[part_name] = LayerBlueprint.from_dict(part_name, matrix)
    _validate_unified_blueprint_rules(mode_part_raw)
    return out


def load_effective_mode_part_config_from_toml_path(
    path: str, *, altitude: AltitudeKey = "mid"
) -> Dict[ModeType, Dict[str, Dict[str, Any]]]:
    """base + part_caps + overrides を合成し、mode→part の有効設定を返す。"""
    p = Path(path)
    with p.open("rb") as f:
        try:
            import tomllib
            data = tomllib.load(f)
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
            data = tomllib.load(f)
    base = data.get("base")
    if not isinstance(base, dict):
        raise ValueError("Unified blueprint TOML must contain [base.*]")
    part_caps = data.get("part_caps")
    if not isinstance(part_caps, dict):
        raise ValueError("Unified blueprint TOML must contain [part_caps.*]")
    overrides = data.get("overrides")
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise ValueError("Unified blueprint TOML [overrides] must be a dict")
    if altitude not in ALTITUDES:
        raise ValueError(f"altitude must be one of {ALTITUDES}, got {altitude!r}")
    mode_part_raw: Dict[ModeType, Dict[str, Dict[str, Any]]] = {}
    for mode in _MODES:
        mode_block = base.get(mode)
        if not isinstance(mode_block, dict):
            raise ValueError(f"Unified blueprint missing base mode section: {mode}")
        mode_part_raw[mode] = {}
        for part_name in PART_NAMES:
            part_block = mode_block.get(part_name)
            if not isinstance(part_block, dict):
                raise ValueError(
                    f"Unified blueprint missing base part section: mode={mode}, part={part_name}"
                )
            effective_block = _deep_copy_dict(part_block)
            caps = part_caps.get(part_name)
            if not isinstance(caps, dict):
                raise ValueError(f"Unified blueprint missing part_caps for part={part_name}")
            legs = effective_block.get("legs")
            if not isinstance(legs, dict):
                raise ValueError(
                    f"Unified blueprint missing base legs: mode={mode}, part={part_name}"
                )
            for leg_key in ("pb", "bps", "cc"):
                if leg_key not in caps or not isinstance(caps[leg_key], bool):
                    raise ValueError(
                        f"Unified blueprint invalid part_caps.{leg_key} for part={part_name}"
                    )
                legs[leg_key] = bool(legs.get(leg_key, False)) and bool(caps[leg_key])
            mode_overrides = overrides.get(mode, {})
            if not isinstance(mode_overrides, dict):
                raise ValueError(f"Unified blueprint invalid overrides for mode={mode}")
            altitude_overrides = mode_overrides.get(altitude, {})
            if not isinstance(altitude_overrides, dict):
                raise ValueError(
                    f"Unified blueprint invalid overrides for mode={mode}, altitude={altitude}"
                )
            part_override = altitude_overrides.get(part_name, {})
            if not isinstance(part_override, dict):
                raise ValueError(
                    f"Unified blueprint invalid override part section: mode={mode}, altitude={altitude}, part={part_name}"
                )
            _deep_merge_dict(effective_block, part_override)
            mode_part_raw[mode][part_name] = effective_block
    return mode_part_raw


def _deep_copy_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = _deep_copy_dict(v)
        else:
            out[k] = v
    return out


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge_dict(base[k], v)
        else:
            base[k] = v


def _validate_unified_blueprint_rules(
    mode_part_raw: Dict[ModeType, Dict[str, Dict[str, Any]]]
) -> None:
    """
    SPEC.md に基づく統合 blueprint の矛盾チェック。
    """
    for mode in _MODES:
        if mode not in mode_part_raw:
            raise ValueError(f"Unified blueprint missing mode section: {mode}")
        row = mode_part_raw[mode]
        for part in PART_NAMES:
            if part not in row:
                raise ValueError(f"Unified blueprint missing part section: mode={mode}, part={part}")
            legs = row[part].get("legs")
            if not isinstance(legs, dict):
                raise ValueError(f"Unified blueprint missing legs: mode={mode}, part={part}")
            for leg_key in ("pb", "bps", "cc"):
                if leg_key not in legs or not isinstance(legs[leg_key], bool):
                    raise ValueError(
                        f"Unified blueprint invalid legs.{leg_key}: mode={mode}, part={part}"
                    )
            if part == "Attitude" and (legs["bps"] or legs["cc"]):
                raise ValueError(f"Unified blueprint invalid legs for Attitude: mode={mode}")
            if part == "Booster" and (legs["pb"] or legs["cc"]):
                raise ValueError(f"Unified blueprint invalid legs for Booster: mode={mode}")
    # Emergency は Main のみ稼働（future 100%）
    em = mode_part_raw["Emergency"]
    if float(em["Attitude"].get("future", 0.0)) != 0.0 or float(em["Booster"].get("future", 0.0)) != 0.0:
        raise ValueError("Unified blueprint invalid Emergency: Attitude/Booster future must be 0.0")
    # Cruise は Booster カット
    cr = mode_part_raw["Cruise"]
    if float(cr["Booster"].get("future", 0.0)) != 0.0:
        raise ValueError("Unified blueprint invalid Cruise: Booster future must be 0.0")
    # モード総量（future）: Boost=2.0, Cruise=1.5, Emergency=1.0
    expected_totals: Dict[ModeType, float] = {"Boost": 2.0, "Cruise": 1.5, "Emergency": 1.0}
    for mode, expected in expected_totals.items():
        total = sum(float(mode_part_raw[mode][p].get("future", 0.0)) for p in PART_NAMES)
        if not math.isclose(total, expected, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"Unified blueprint invalid future total for {mode}: expected {expected}, got {total}"
            )
