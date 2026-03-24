"""
AttitudePart：姿勢制御部分。Micro先物＋PB。CC/BPSは装着不可。

Blueprint により比率・枚数を決定。定義書「1-1」「1-4」「5-1」「5-2」参照。
"""

from __future__ import annotations

from typing import Literal

from .base_part import BasePart


class AttitudePart(BasePart):
    """姿勢制御部分：Micro先物＋PB。定義書「1-1」「5-1」「5-2」参照。"""

    LAYER_TYPE: Literal["MINI", "MICRO"] = "MICRO"
    PART_NAME: str = "AttitudePart"
