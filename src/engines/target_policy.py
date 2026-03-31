"""
DB base(target) と Blueprint 比率から mode連動の future target を解決する。
"""
from __future__ import annotations

from typing import Dict

from cockpit.mode import ModeType

from .blueprint import ALTITUDES, LayerBlueprint, PART_NAMES, load_blueprints_from_unified_toml_path


def resolve_future_targets_by_part(
    blueprints: Dict[str, LayerBlueprint],
    *,
    mode: ModeType,
    base_target: float,
) -> Dict[str, float]:
    """Part ごとの future target（MNQ/MGC 相当）を返す。"""
    out: Dict[str, float] = {}
    base = float(base_target)
    for part in PART_NAMES:
        ratios = blueprints[part].get_ratios(mode)
        out[part] = float(ratios["future"]) * base
    return out


def resolve_future_targets_by_part_from_toml(
    toml_path: str,
    *,
    mode: ModeType,
    altitude: str,
    base_target: float,
) -> Dict[str, float]:
    """統合 TOML と高度から Part ごとの future target を解決する。"""
    a = str(altitude).strip().lower()
    if a not in ALTITUDES:
        raise ValueError(f"altitude must be one of {ALTITUDES}, got {altitude!r}")
    blueprints = load_blueprints_from_unified_toml_path(
        toml_path, altitude=a  # type: ignore[arg-type]
    )
    return resolve_future_targets_by_part(blueprints, mode=mode, base_target=base_target)


def total_future_target(
    blueprints: Dict[str, LayerBlueprint],
    *,
    mode: ModeType,
    base_target: float,
) -> float:
    """mode連動の全Part future target 合計。"""
    parts = resolve_future_targets_by_part(
        blueprints, mode=mode, base_target=base_target
    )
    return sum(parts[p] for p in PART_NAMES)
