from __future__ import annotations

from typing import Dict

PositionLegs = Dict[str, float]
PositionLegsBySymbol = Dict[str, PositionLegs]

PositionContractDetail = Dict[str, float]
PositionDetailByType = Dict[str, PositionContractDetail]
PositionDetailBySymbol = Dict[str, PositionDetailByType]
