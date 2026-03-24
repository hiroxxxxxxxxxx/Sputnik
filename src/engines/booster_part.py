"""
BoosterPart：ブースター部分。Micro先物＋BPS。Boost時のみ稼働。

Blueprint により比率・枚数を決定。定義書「1-1」「1-4」「1-5」「5-2」参照。
"""

from __future__ import annotations

from typing import Literal

from .base_part import BasePart


class BoosterPart(BasePart):
    """ブースター部分：Micro先物＋BPS。Boost時のみ稼働。定義書「1-1」「1-4」「1-5」参照。"""

    LAYER_TYPE: Literal["MINI", "MICRO"] = "MICRO"
    PART_NAME: str = "BoosterPart"
