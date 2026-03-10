"""
AttitudePart：姿勢制御部分。Micro先物＋PB。CC/BPSは装着不可。

Blueprint により比率・枚数を決定。定義書「1-1」「1-4」「5-1」「5-2」参照。
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from .blueprint import LayerBlueprint, contract_size, contract_symbol
from .deltas import PartDelta


class AttitudePart:
    """
    姿勢制御部分：Micro先物＋PB。CC/BPSは装着不可。

    Part は FlightController も「モード」も参照しない。
    Engine から渡される物理的な目標を入力として、不足分（差分）を算出する。
    定義書「1-1」「5-1」「5-2」参照。
    """

    LAYER_TYPE: Literal["MINI", "MICRO"] = "MICRO"

    def __init__(
        self,
        blueprint: LayerBlueprint,
        symbol_type: Literal["NQ", "GC"],
    ) -> None:
        """
        :param blueprint: 姿勢制御層の設計図
        :param symbol_type: 銘柄（NQ or GC）
        """
        self.blueprint = blueprint
        self.symbol_type = symbol_type
        self._last_instruction: Optional[Dict[str, Any]] = None
        self._is_main_engine: bool = False

    @property
    def contract_symbol(self) -> str:
        """発注用契約シンボル。Attitude は MICRO。"""
        return contract_symbol(self.symbol_type, self.LAYER_TYPE)

    @property
    def contract_size(self) -> float:
        """1単位あたりの重み。Attitude は 0.1。"""
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
                        detail=f"AttitudePart {leg}: target={t} actual={a}",
                    )
                )
        return out
