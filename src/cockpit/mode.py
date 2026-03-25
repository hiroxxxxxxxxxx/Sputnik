"""
スロットルモード定数・承認モード型の単一定義（共有層）。

cockpit, engines, reports, store の共通基盤。パッケージ依存の方向は cockpit.mode を最下流として、
上位パッケージ（engines, reports, store）がここから import する。
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

ApprovalMode = Literal["Manual", "SemiAuto", "Auto"]
