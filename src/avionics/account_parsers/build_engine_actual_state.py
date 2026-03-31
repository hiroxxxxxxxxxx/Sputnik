from __future__ import annotations

from typing import Dict

from avionics.data.account_state import EngineActualState

from .build_actual_by_target import build_actual_by_target


def build_engine_actual_state(
    symbol_actual: Dict[str, float], target_futures_by_part: Dict[str, float]
) -> EngineActualState:
    return build_actual_by_target(symbol_actual, target_futures_by_part)


def build_engine_part_on_off_state(
    symbol_actual: Dict[str, float], target_futures_by_part: Dict[str, float]
) -> Dict[str, bool]:
    actual_state = build_engine_actual_state(symbol_actual, target_futures_by_part)
    return {part: abs(float(actual_state[part]["future"])) > 0.0 for part in ("Main", "Attitude", "Booster")}
