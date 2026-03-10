"""
Inventory（在庫管理）：Blueprint と BaseUnitCount から目標ポジション（Target）を算出する。

全層の比率を合算し、ネット（相殺）後の先物・オプション K1/K2 の目標枚数を返す。
執行層（ib_async 等）は Target と Actual（IBKR ポジション）の差分のみ発注する。
定義書「1-4」「6-2」参照。
"""

from __future__ import annotations

from typing import Dict, Literal

from .blueprint import LayerBlueprint, ModeType, RATIO_KEYS


class EngineInventory:
    """
    エンジンの物理的な持ち高（Target）を計算・保持する。

    1. 各層の Blueprint を合算
    2. BaseUnitCount を乗算
    3. 現在の IBKR ポジションとの差分は執行層で算出（本クラスは Target のみ）

    定義書「0-1-Ⅵ」: 暴落時も設計図に従い自己改造しない。
    """

    def __init__(
        self,
        symbol: Literal["NQ", "GC"],
        blueprints: Dict[str, LayerBlueprint],
    ) -> None:
        """
        :param symbol: 銘柄（NQ or GC）。発注先の識別用。
        :param blueprints: 層名 → LayerBlueprint。例: {"Main": bp_main, "Attitude": bp_att, "Booster": bp_booster}
        定義書「1-1」参照。
        """
        self.symbol: Literal["NQ", "GC"] = symbol
        self.blueprints: Dict[str, LayerBlueprint] = dict(blueprints)

    def calculate_net_targets(
        self,
        mode: ModeType,
        base_unit: float,
    ) -> Dict[str, float]:
        """
        全層をスキャンし、ネット（相殺）後の目標枚数を返す。

        BaseUnitCount（価格・資産額から算出）を各層の比率で乗じ、合算する。
        定義書「1-4」比率と「6-2」段階的パージの前提となる Target 算出。

        :param mode: 現在のスロットルモード。
        :param base_unit: 基本束数（1 単位あたりの枚数ベース）。価格や資産額から算出。
        :return: future, k1, k2 の目標枚数（round 済み）。キーは "future", "k1", "k2"。
        """
        total_f = 0.0
        total_k1 = 0.0
        total_k2 = 0.0
        for _name, bp in self.blueprints.items():
            ratios = bp.get_ratios(mode)
            total_f += float(ratios["future"]) * base_unit
            total_k1 += float(ratios["option_k1"]) * base_unit
            total_k2 += float(ratios["option_k2"]) * base_unit
        return {
            "future": round(total_f),
            "k1": round(total_k1),
            "k2": round(total_k2),
        }
