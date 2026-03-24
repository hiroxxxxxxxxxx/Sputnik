"""
ブループリント（設計図）：モード別の比率・戦略を保持する読み取り専用のデータ層。

TOML/JSON のマトリクスデータをロードし、起動時に検証したうえで frozen なデータクラスとして保持する。
実行中の書き換えを防ぎ、定義書「0-1-Ⅵ」の自己改造禁止を体現する。
層タイプ（MINI/MICRO）と発注用 contract_symbol / contract_size もここで定義。
定義書「1-3」「1-4」参照。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Tuple

from cockpit.mode import ModeType, MODES

# 層タイプ（Main=MINI, Attitude/Booster=MICRO）。発注先・重み算出に使用。
LayerType = Literal["MINI", "MICRO"]


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
    :param path: config/blueprints/main_layer.toml などのパス。Python 3.11+ は tomllib、それ以前は tomli を使用。
    """
    with open(path, "rb") as f:
        try:
            import tomllib
            data = tomllib.load(f)
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
            data = tomllib.load(f)
    return LayerBlueprint.from_toml_dict(name=name, data=data)
