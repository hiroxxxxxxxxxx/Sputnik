"""
差分データ（Part → Engine）。

Part は注文や API を知らず、Inventory と Blueprint から「不足分（差分）」の純データのみを算出する。
Engine が差分を集約し、ExecutionProvider に渡して執行へ変換する。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartDelta:
    """Part が算出する「不足分（差分）」の純データ。"""

    leg: str
    qty: float
    detail: str

