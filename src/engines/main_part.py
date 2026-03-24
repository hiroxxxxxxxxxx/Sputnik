"""
MainPart：メイン部分。Mini先物＋PB/BPS。CCはCruiseでメインのみオン。

Blueprint により比率・枚数を決定。定義書「1-1」「1-4」「1-5」参照。
"""

from __future__ import annotations

from typing import Literal

from .base_part import BasePart


class MainPart(BasePart):
    """メイン部分：Mini先物＋PB＋BPS。定義書「1-1」「1-4」「5-1」参照。"""

    LAYER_TYPE: Literal["MINI", "MICRO"] = "MINI"
    PART_NAME: str = "MainPart"
