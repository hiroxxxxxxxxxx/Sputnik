from __future__ import annotations

from typing import Dict

from engines.blueprint import PART_NAMES


def build_actual_by_target(
    symbol_actual: Dict[str, float],
    target_futures_by_part: Dict[str, float],
) -> Dict[str, Dict[str, float]]:
    missing = [p for p in PART_NAMES if p not in target_futures_by_part]
    if missing:
        raise ValueError(f"target_futures missing part rows: {missing}")
    weights = {p: abs(float(target_futures_by_part[p])) for p in PART_NAMES}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("mode-aware target total weight must be > 0")
    out: Dict[str, Dict[str, float]] = {}
    for part in PART_NAMES:
        share = weights[part] / total_weight
        out[part] = {
            "future": float(symbol_actual["future"]) * share,
            "k1": float(symbol_actual["k1"]) * share,
            "k2": float(symbol_actual["k2"]) * share,
        }
    return out
