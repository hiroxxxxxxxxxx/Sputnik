"""
Engine（推進層）：NQ専用 or GC専用の1インスタンス。Blueprint で設計図を保持。

管制からモードを受け取り、各 Part（Blueprint ベース）に伝播。StrategyBundle は廃止済み。
定義書「1-1」「1-3」「0-1-Ⅵ」参照。
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from .blueprint import LayerBlueprint, ModeType
from .deltas import PartDelta
from .main_part import MainPart
from .attitude_part import AttitudePart
from .booster_part import BoosterPart
from .inventory import EngineInventory


class Engine:
    """
    NQ専用 or GC専用のエンジン。3層は Part で表現（各層は LayerBlueprint を保持）。

    管制（FlightController）から apply_mode(mode) で指令を受け、各 Part に伝播。
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
        self.main_part: MainPart = MainPart(
            self.blueprints["Main"], symbol_type
        )
        self.attitude_part: AttitudePart = AttitudePart(
            self.blueprints["Attitude"], symbol_type
        )
        self.booster_part: BoosterPart = BoosterPart(
            self.blueprints["Booster"], symbol_type
        )
        self.inventory: EngineInventory = EngineInventory(
            symbol=symbol_type, blueprints=self.blueprints
        )

    def _instruction_for(self, mode: ModeType) -> Dict[str, Any]:
        """
        config から base_unit / boost_ratio を参照し、Part に渡す指示を返す。
        base_unit, boost_ratio は大元で必須。欠けていれば KeyError。
        定義書「1-3」「1-4」参照。
        """
        return {
            "base_unit": self.config["base_unit"],
            "boost_ratio": self.config["boost_ratio"],
        }

    def _target_for_part(self, part_name: str, mode: ModeType, base: float) -> Dict[str, float]:
        """指定 Part の設計図からモード別目標枚数を算出。Engine が翻訳し Part には数値のみ渡す。"""
        bp = self.blueprints[part_name]
        r = bp.get_ratios(mode)
        return {
            "future": float(r["future"]) * base,
            "k1": float(r["option_k1"]) * base,
            "k2": float(r["option_k2"]) * base,
        }

    async def apply_mode(self, mode: ModeType) -> None:
        """
        管制からモード指令を受け、抽象モードを「目標値」に翻訳して各 Part に渡す。
        Part はモードを知らず、目標（target）と現在（actual）の差分のみ算出。Engine が差分を集約し執行へ渡す。
        定義書「1-4」「1-5」「Phase 4」参照。
        """
        base = self.config["base_unit"]
        actual = None
        all_deltas: list[PartDelta] = []
        for part_name, part in (
            ("Main", self.main_part),
            ("Attitude", self.attitude_part),
            ("Booster", self.booster_part),
        ):
            target = self._target_for_part(part_name, mode, base)
            all_deltas.extend(part.calculate_deltas(target=target, actual=actual))
        # 差分を ExecutionProvider に渡して執行するのは Engine の責務。未注入時は収集のみ。
        if all_deltas and getattr(self, "_executor", None) is not None:
            await self._executor.execute(all_deltas)

    def sync(self) -> None:
        """
        【シンボル・変換】各 Part の sync を呼ぶ。
        段階的パージ（6-2）: Booster → Attitude → Main の順。定義書「6-2」参照。
        """
        self.booster_part.sync()
        self.attitude_part.sync()
        self.main_part.sync()

    def calculate_net_targets(self, mode: ModeType, base_unit: float) -> Dict[str, float]:
        """
        ブループリントに基づき、指定モード・基本束数でのネット目標枚数を返す。
        定義書「1-4」「6-2」参照。
        """
        return self.inventory.calculate_net_targets(mode=mode, base_unit=base_unit)
