"""
Engine（推進層）：NQ専用 or GC専用の1インスタンス。Blueprint で設計図を保持。

管制からモードを受け取り、Blueprint ベースで目標差分を算出。
定義書「1-1」「1-3」「0-1-Ⅵ」参照。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from .blueprint import (
    LayerBlueprint,
    ModeType,
    PART_LAYER_TYPES,
    PART_NAMES,
    contract_size,
    contract_symbol,
)


@dataclass(frozen=True)
class PartDelta:
    """Engine が算出する「不足分（差分）」の純データ。"""

    leg: str
    qty: float
    detail: str


def calculate_net_targets(
    blueprints: Dict[str, LayerBlueprint],
    mode: ModeType,
    base_unit: float,
) -> Dict[str, float]:
    """
    全層をスキャンし、ネット（相殺）後の目標枚数を返す。

    BaseUnitCount（価格・資産額から算出）を各層の比率で乗じ、合算する。
    定義書「1-4」比率と「6-2」段階的パージの前提となる Target 算出。

    :param blueprints: 層名 → LayerBlueprint。
    :param mode: 現在のスロットルモード。
    :param base_unit: 基本束数（1 単位あたりの枚数ベース）。
    :return: future, k1, k2 の目標枚数（round 済み）。
    """
    total_f = 0.0
    total_k1 = 0.0
    total_k2 = 0.0
    for _name, bp in blueprints.items():
        ratios = bp.get_ratios(mode)
        total_f += float(ratios["future"]) * base_unit
        total_k1 += float(ratios["option_k1"]) * base_unit
        total_k2 += float(ratios["option_k2"]) * base_unit
    return {
        "future": round(total_f),
        "k1": round(total_k1),
        "k2": round(total_k2),
    }


class Engine:
    """
    NQ専用 or GC専用のエンジン。3層（Main / Attitude / Booster）は Blueprint で表現。

    管制（FlightController）から apply_mode(mode) で指令を受け、Blueprint ベースで差分を算出。
    blueprints 必須。config で base_unit 等を保持。定義書「1-1」ユニット構成参照。
    """

    def __init__(
        self,
        symbol_type: Literal["NQ", "GC"],
        blueprints: Dict[str, LayerBlueprint],
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        エンジンを初期化する。

        :param symbol_type: 本エンジンの銘柄（NQ or GC）
        :param blueprints: 層名→LayerBlueprint。Main / Attitude / Booster の3キーを想定
        :param config: 銘柄固有設定（base_unit, boost_ratio 必須）。TOML 等から注入想定。None の場合は ValueError。
        定義書「1-1」「1-3」参照。
        """
        if config is None:
            raise ValueError(
                "config is required. Provide a dict with at least 'base_unit' and 'boost_ratio' from the top level."
            )
        self.symbol_type: Literal["NQ", "GC"] = symbol_type
        self.config: Dict[str, Any] = dict(config)
        self.blueprints: Dict[str, LayerBlueprint] = dict(blueprints)

    def contract_symbol_for(self, part_name: str) -> str:
        """指定 Part の発注用シンボルを返す。"""
        return contract_symbol(self.symbol_type, PART_LAYER_TYPES[part_name])

    def contract_size_for(self, part_name: str) -> float:
        """指定 Part の1単位あたりの重みを返す。"""
        return contract_size(PART_LAYER_TYPES[part_name])

    def _target_for_part(self, part_name: str, mode: ModeType, base: float) -> Dict[str, float]:
        """指定 Part の設計図からモード別目標枚数を算出。"""
        bp = self.blueprints[part_name]
        r = bp.get_ratios(mode)
        return {
            "future": float(r["future"]) * base,
            "k1": float(r["option_k1"]) * base,
            "k2": float(r["option_k2"]) * base,
        }

    def calculate_deltas(
        self,
        part_name: str,
        *,
        target: Dict[str, float],
        actual: Optional[Dict[str, float]] = None,
    ) -> List[PartDelta]:
        """
        目標（target）と現在（actual）の差分を算出する。

        :param part_name: 層名（Main / Attitude / Booster）
        :param target: {"future": x, "k1": y, "k2": z} のような目標枚数
        :param actual: 同キーの現在枚数。未指定なら全て 0 とみなす（暫定）
        """
        actual = dict(actual or {})
        out: list[PartDelta] = []
        for leg in ("future", "k1", "k2"):
            t = float(target.get(leg, 0.0))
            a = float(actual.get(leg, 0.0))
            d = t - a
            if d != 0.0:
                out.append(
                    PartDelta(
                        leg=leg,
                        qty=d,
                        detail=f"{part_name} {leg}: target={t} actual={a}",
                    )
                )
        return out

    async def apply_mode(
        self,
        mode: ModeType,
        *,
        actual_by_part: Optional[Dict[str, Dict[str, float]]] = None,
        target_futures_by_part: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        管制からモード指令を受け、抽象モードを「目標値」に翻訳して差分を算出。
        Blueprint ベースで不足分を集約し、ExecutionProvider に渡す。
        定義書「1-4」「1-5」「Phase 4」参照。
        """
        base = self.config["base_unit"]
        all_deltas: list[PartDelta] = []
        for part_name in PART_NAMES:
            target = self._target_for_part(part_name, mode, base)
            if target_futures_by_part is not None and part_name in target_futures_by_part:
                target["future"] = float(target_futures_by_part[part_name])
            part_actual = (
                actual_by_part.get(part_name, None)
                if actual_by_part is not None
                else None
            )
            all_deltas.extend(
                self.calculate_deltas(part_name, target=target, actual=part_actual)
            )
        if all_deltas and getattr(self, "_executor", None) is not None:
            await self._executor.execute(all_deltas)

    def sync(self) -> None:
        """
        【予約】実行反映は Engine/Provider が担う。
        段階的パージ（6-2）: Booster → Attitude → Main の順。定義書「6-2」参照。
        """
        pass

    def calculate_net_targets(self, mode: ModeType, base_unit: float) -> Dict[str, float]:
        """
        ブループリントに基づき、指定モード・基本束数でのネット目標枚数を返す。
        定義書「1-4」「6-2」参照。
        """
        return calculate_net_targets(self.blueprints, mode=mode, base_unit=base_unit)
