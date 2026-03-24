"""
Part 共通基底。calculate_deltas / contract_* / sync を持つ。

サブクラスは LAYER_TYPE と Part 名のみ定義すれば良い。
定義書「1-1」「1-4」「5-1」参照。
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from .blueprint import LayerBlueprint, contract_size, contract_symbol
from .deltas import PartDelta


class BasePart:
    """
    Part 共通基底。Engine から渡される目標と現在値の差分を算出する。

    Part は FlightController も「モード」も参照しない。
    Engine から渡される物理的な目標（比率・枚数）を入力として、不足分（差分）を算出する。
    """

    LAYER_TYPE: Literal["MINI", "MICRO"] = "MICRO"
    PART_NAME: str = "BasePart"

    def __init__(
        self,
        blueprint: LayerBlueprint,
        symbol_type: Literal["NQ", "GC"],
    ) -> None:
        self.blueprint = blueprint
        self.symbol_type = symbol_type

    @property
    def contract_symbol(self) -> str:
        return contract_symbol(self.symbol_type, self.LAYER_TYPE)

    @property
    def contract_size(self) -> float:
        return contract_size(self.LAYER_TYPE)

    def sync(self) -> None:
        """【予約】実行反映は Engine/Provider が担う。Part は差分算出のみ。"""
        pass

    def calculate_deltas(
        self,
        *,
        target: Dict[str, float],
        actual: Optional[Dict[str, float]] = None,
    ) -> List[PartDelta]:
        """
        目標（target）と現在（actual）の差分を算出する。Part は数値のみを返す。

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
                        detail=f"{self.PART_NAME} {leg}: target={t} actual={a}",
                    )
                )
        return out
