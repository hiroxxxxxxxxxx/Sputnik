from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from avionics.account_parsers import build_option_strategy_state_from_rows
from avionics.data.futures_micro_equiv import (
    engine_symbol_to_micro_notional_label,
    micro_equivalent_net_gc_family,
    micro_equivalent_net_nq_family,
)
from cockpit.mode import ModeType
from engines.blueprint import PART_NAMES, load_blueprints_from_unified_toml_path
from engines.target_policy import total_future_target

_STRATEGY_NAMES = ("PB", "BPS", "CC", "UNCLASSIFIED")


def _default_blueprints(*, altitude: str) -> dict[str, Any]:
    root = Path(__file__).resolve().parent.parent.parent
    path = root / "config" / "targets.toml"
    return load_blueprints_from_unified_toml_path(str(path), altitude=altitude)  # type: ignore[arg-type]


def _build_position_rows(
    symbols: list[str],
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, float]]:
    if not positions_detail:
        return [], [], {}
    futures_rows: list[dict[str, str]] = []
    options_rows: list[dict[str, str]] = []
    futures_actual_net: dict[str, float] = {}
    for sym in symbols:
        detail = positions_detail.get(sym)
        if detail is None:
            continue
        fut = detail.get("futures", {})
        opt = detail.get("options", {})
        futures_rows.append(
            {
                "symbol": sym,
                "nq_buy": f"{float(fut.get('nq_buy', 0.0)):.0f}",
                "nq_sell": f"{float(fut.get('nq_sell', 0.0)):.0f}",
                "mnq_buy": f"{float(fut.get('mnq_buy', 0.0)):.0f}",
                "mnq_sell": f"{float(fut.get('mnq_sell', 0.0)):.0f}",
                "gc_buy": f"{float(fut.get('gc_buy', 0.0)):.0f}",
                "gc_sell": f"{float(fut.get('gc_sell', 0.0)):.0f}",
                "mgc_buy": f"{float(fut.get('mgc_buy', 0.0)):.0f}",
                "mgc_sell": f"{float(fut.get('mgc_sell', 0.0)):.0f}",
            }
        )
        if sym == "NQ":
            futures_actual_net[sym] = micro_equivalent_net_nq_family(fut)
        elif sym == "GC":
            futures_actual_net[sym] = micro_equivalent_net_gc_family(fut)
        options_rows.append({"symbol": sym, **{k: float(v) for k, v in opt.items()}})
    return futures_rows, options_rows, futures_actual_net


def _build_options_strategy_rows(
    symbols: list[str],
    options_rows: list[dict[str, Any]],
    target_base_by_symbol: Optional[dict[str, float]],
    modes_by_symbol: dict[str, ModeType],
    *,
    altitude: str,
) -> list[dict[str, str]]:
    if not options_rows:
        return []
    root = Path(__file__).resolve().parent.parent.parent
    targets_path = str(root / "config" / "targets.toml")
    from engines.blueprint import load_effective_mode_part_config_from_toml_path

    effective = load_effective_mode_part_config_from_toml_path(
        targets_path, altitude=altitude  # type: ignore[arg-type]
    )
    blueprints = _default_blueprints(altitude=altitude)
    strategy_state_by_symbol = build_option_strategy_state_from_rows(symbols, options_rows)
    out: list[dict[str, str]] = []
    for sym in symbols:
        if sym not in ("NQ", "GC"):
            continue
        if sym not in strategy_state_by_symbol:
            continue
        strategy_states = strategy_state_by_symbol[sym]
        futures_target = 0.0
        if target_base_by_symbol is not None and sym in target_base_by_symbol:
            futures_target = total_future_target(
                blueprints,
                mode=modes_by_symbol[sym],
                base_target=float(target_base_by_symbol[sym]),
            )
        legs_active = {"PB": False, "BPS": False, "CC": False}
        part_conf = effective[modes_by_symbol[sym]]
        for part in PART_NAMES:
            legs = part_conf[part]["legs"]
            legs_active["PB"] = legs_active["PB"] or bool(legs.get("pb", False))
            legs_active["BPS"] = legs_active["BPS"] or bool(legs.get("bps", False))
            legs_active["CC"] = legs_active["CC"] or bool(legs.get("cc", False))
        targets = {
            "PB": futures_target if legs_active["PB"] else 0.0,
            "BPS": futures_target if legs_active["BPS"] else 0.0,
            "CC": futures_target if legs_active["CC"] else 0.0,
            "UNCLASSIFIED": 0.0,
        }
        for strat in _STRATEGY_NAMES:
            t = float(targets[strat])
            state = strategy_states[strat]
            a = float(state.qty)
            out.append(
                {
                    "symbol": sym,
                    "strategy": strat,
                    "target": f"{t:.0f}",
                    "actual": f"{a:.0f}",
                    "delta": f"{(t-a):.0f}",
                    "attached": str(state.attached),
                    "unclassified_detail": (
                        ""
                        if strat != "UNCLASSIFIED"
                        else (
                            "P B="
                            f"{float(state.unclassified_detail.put_buy if state.unclassified_detail else 0.0):.0f} "
                            "S="
                            f"{float(state.unclassified_detail.put_sell if state.unclassified_detail else 0.0):.0f} | "
                            "C B="
                            f"{float(state.unclassified_detail.call_buy if state.unclassified_detail else 0.0):.0f} "
                            "S="
                            f"{float(state.unclassified_detail.call_sell if state.unclassified_detail else 0.0):.0f}"
                        )
                    ),
                }
            )
    return out


def _build_futures_target_rows(
    symbols: list[str],
    futures_actual_net: dict[str, float],
    target_base_by_symbol: Optional[dict[str, float]],
    modes_by_symbol: dict[str, ModeType],
    *,
    altitude: str,
) -> list[dict[str, str]]:
    if target_base_by_symbol is None:
        return []
    blueprints = _default_blueprints(altitude=altitude)
    rows: list[dict[str, str]] = []
    for sym in symbols:
        if sym not in ("NQ", "GC"):
            continue
        if sym not in target_base_by_symbol:
            raise ValueError(f"target_base_futures missing engine symbol: {sym}")
        mode = modes_by_symbol[sym]
        target_total = total_future_target(
            blueprints,
            mode=mode,
            base_target=float(target_base_by_symbol[sym]),
        )
        actual_net = float(futures_actual_net.get(sym, 0.0))
        delta = target_total - actual_net
        rows.append(
            {
                "symbol": sym,
                "micro_label": engine_symbol_to_micro_notional_label(sym),
                "target": f"{target_total:.0f}",
                "actual": f"{actual_net:.0f}",
                "delta": f"{delta:.0f}",
            }
        )
    return rows


def build_position_report_context(
    symbols: list[str],
    *,
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]],
    target_base_by_symbol: Optional[dict[str, float]],
    modes_by_symbol: dict[str, ModeType],
    altitude: str,
) -> dict[str, Any]:
    futures_rows, options_raw_rows, futures_actual_net = _build_position_rows(
        symbols, positions_detail
    )
    options_rows = _build_options_strategy_rows(
        symbols,
        options_raw_rows,
        target_base_by_symbol,
        modes_by_symbol,
        altitude=altitude,
    )
    futures_target_rows = _build_futures_target_rows(
        symbols,
        futures_actual_net,
        target_base_by_symbol,
        modes_by_symbol,
        altitude=altitude,
    )
    return {
        "symbols": symbols,
        "futures_rows": futures_rows,
        "options_rows": options_rows,
        "futures_target_rows": futures_target_rows,
    }
