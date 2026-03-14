"""
スロットルモードの単一定義。Boost / Cruise / Emergency の文字列定数と型。

Cockpit が get_effective_level の 0/1/2 をこのモードに変換し、Engine へ apply_mode する。
Engine / Blueprint も同じ定義を参照して get_ratios(mode) 等で使用する。
定義書「4-2 Effective Level × スロットルモード対応表」参照。
"""

from __future__ import annotations

from typing import Literal, Tuple

BOOST = "Boost"
CRUISE = "Cruise"
EMERGENCY = "Emergency"

MODES: Tuple[str, ...] = (BOOST, CRUISE, EMERGENCY)

ModeType = Literal["Boost", "Cruise", "Emergency"]
