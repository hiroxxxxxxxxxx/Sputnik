from __future__ import annotations

from typing import TYPE_CHECKING, Any

from avionics.compute import price_signals_p_input_tuple
from reports.breakdown.common import BREAKDOWN_LEVEL_STR

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import SignalBundle


def _scl_level_for_breakdown(fc: "FlightController") -> int:
    getter = getattr(fc, "get_synchronous_control_level", None)
    if callable(getter):
        return int(getter())
    from avionics.factors.t_factor import TFactor

    t_levels: list[int] = []
    for factors in fc.mapping.symbol_factors.values():
        for fac in factors:
            if isinstance(fac, TFactor):
                t_levels.append(int(fac.level))
                break
    if not t_levels:
        return 0
    if len(t_levels) == 1:
        return t_levels[0]
    if all(lv == 2 for lv in t_levels):
        return 2
    if any(lv == 2 for lv in t_levels):
        return 1
    return 0


def build_t_section(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> dict[str, Any] | None:
    if not price_symbols:
        return None
    rows = [{"symbol": sym, "trend": str(price_signals_p_input_tuple(bundle.price_signals[sym])[3])} for sym in price_symbols]
    return {"scl_level": BREAKDOWN_LEVEL_STR.get(_scl_level_for_breakdown(fc), "?"), "rows": rows}


def _default_t_section() -> dict[str, Any]:
    return {
        "scl_level": "0",
        "rows": [
            {"symbol": "NQ", "trend": "—"},
            {"symbol": "GC", "trend": "—"},
        ],
    }


def build_fixed_t_section(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> dict[str, str]:
    t_sec = build_t_section(fc, bundle, price_symbols) or _default_t_section()
    rows_by_symbol = {row["symbol"]: row for row in t_sec.get("rows", [])}
    return {
        "scl_level": t_sec.get("scl_level", "0"),
        "nq_trend": rows_by_symbol.get("NQ", {"trend": "—"})["trend"],
        "gc_trend": rows_by_symbol.get("GC", {"trend": "—"})["trend"],
    }
