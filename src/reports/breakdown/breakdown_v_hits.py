"""breakdown レポート用: V ★ 付与キー集合。"""

from __future__ import annotations

from typing import Any

from avionics.factors.v_factor import v_index_meets_on_band


def v_breakdown_hit_row_keys(vs: Any, v_th: dict | None, v_level: int, v1_days: int) -> set[str]:
    """指数行・V2 復帰行・V1 復帰・ノックイン行の row_key 集合（mark_hits 用）。"""
    keys: set[str] = set()
    if v_th is not None and v_index_meets_on_band(vs.index_value, v_th):
        keys.add("index_value")
    if v_level == 2:
        keys.add("v2_recovery")
    if v_level == 1:
        keys.add("v1_recovery")
        if vs.recovery_confirm_satisfied_days_v1_off >= v1_days:
            keys.add("v1_knock_in")
    return keys
