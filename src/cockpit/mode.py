"""
スロットルモード定数の単一定義（共有層）。Boost / Cruise / Emergency の文字列定数と型。

cockpit, engines, reports の共通基盤。パッケージ依存の方向は cockpit.mode を最下流として、
上位パッケージ（engines, reports）がここから import する。
定義書「4-2 Effective Level × スロットルモード対応表」参照。
"""

from __future__ import annotations

from typing import Literal, Tuple

BOOST = "Boost"
CRUISE = "Cruise"
EMERGENCY = "Emergency"

MODES: Tuple[str, ...] = (BOOST, CRUISE, EMERGENCY)

ModeType = Literal["Boost", "Cruise", "Emergency"]

MODE_STR: dict[int, str] = {0: BOOST, 1: CRUISE, 2: EMERGENCY}
