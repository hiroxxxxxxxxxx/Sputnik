"""
MainPart：メイン部分。Mini先物＋PB/BPS。CCはCruiseでメインのみオン。

Blueprint により比率・枚数を決定。定義書「1-1」「1-4」「1-5」参照。
"""

from __future__ import annotations

from typing import Dict, Literal, Optional

from .blueprint import LayerBlueprint, contract_size, contract_symbol
from .deltas import PartDelta


class MainPart:
    """
    メイン部分：Mini先物＋PB＋BPS。CCはCruise時のみ稼働。

    Part は FlightController も「モード」も参照しない。
    Engine から渡される物理的な目標（比率・枚数など）を入力として、不足分（差分）を算出する。
    定義書「1-1」「1-4」「5-1」参照。
    """

    LAYER_TYPE: Literal["MINI", "MICRO"] = "MINI"

    def __init__(
        self,
        blueprint: LayerBlueprint,
        symbol_type: Literal["NQ", "GC"],
    ) -> None:
        """
        :param blueprint: メイン層の設計図
        :param symbol_type: 銘柄（NQ or GC）
        """
        self.blueprint = blueprint
        self.symbol_type = symbol_type
        self._is_main_engine: bool = True  # CC はメインのみ（定義書 5-1）

    @property
    def contract_symbol(self) -> str:
        """発注用契約シンボル。Main は MINI。"""
        return contract_symbol(self.symbol_type, self.LAYER_TYPE)

    @property
    def contract_size(self) -> float:
        """1単位あたりの重み。Main は 1.0。"""
        return contract_size(self.LAYER_TYPE)

    def sync(self) -> None:
        """【予約】実行反映は Engine/Provider が担う。Part は差分算出のみ。"""
        pass

    def calculate_deltas(
        self,
        *,
        target: Dict[str, float],
        actual: Optional[Dict[str, float]] = None,
    ) -> list[PartDelta]:
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
                        detail=f"MainPart {leg}: target={t} actual={a}",
                    )
                )
        return out
