from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class UnclassifiedDetail:
    put_buy: float
    put_sell: float
    call_buy: float
    call_sell: float


@dataclass(frozen=True)
class OptionStrategyState:
    strategy: str
    qty: float
    attached: bool
    unclassified_detail: UnclassifiedDetail | None = None


@dataclass(frozen=True)
class DailyEnginePartState:
    part: str
    engine_on: bool
    strategy_name: str


@dataclass(frozen=True)
class DailySymbolState:
    symbol: str
    rows: tuple[DailyEnginePartState, DailyEnginePartState, DailyEnginePartState]


EnginePartActual = Dict[str, float]
EngineActualState = Dict[str, EnginePartActual]
