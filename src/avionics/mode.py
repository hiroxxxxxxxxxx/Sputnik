"""
スロットルモードの単一定義。Boost / Cruise / Emergency の文字列定数と型。

Cockpit・FlightController・Engine/Blueprint が同じ定義を参照し、文字列の二重定義を避ける。
定義書「4-2 Effective Level × スロットルモード対応表」参照。
"""

from __future__ import annotations

from typing import Literal, Tuple

BOOST = "Boost"
CRUISE = "Cruise"
EMERGENCY = "Emergency"

MODES: Tuple[str, ...] = (BOOST, CRUISE, EMERGENCY)

ModeType = Literal["Boost", "Cruise", "Emergency"]
