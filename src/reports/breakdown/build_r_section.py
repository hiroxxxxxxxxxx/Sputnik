from __future__ import annotations

from typing import TYPE_CHECKING, Any

from avionics.compute import liquidity_tip_canonical_drawdown
from reports.breakdown.common import breakdown_level_suffix, fmt_pct, fmt_price, mark_value_keys, value_entry

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import SignalBundle


def _first_factor_among_symbols(fc: "FlightController", symbols: list[str], cls: type) -> Any:
    for sym in symbols:
        for f in fc.mapping.symbol_factors.get(sym, []):
            if isinstance(f, cls):
                return f
    return None


def build_r_section(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> dict[str, Any] | None:
    from avionics.factors.r_factor import RFactor

    r_fac = _first_factor_among_symbols(fc, price_symbols, RFactor)
    if not bundle.liquidity_tip:
        return None
    lt = bundle.liquidity_tip
    values = {
        "last_close": value_entry(fmt_price(lt.last_close)),
        "tip_reference_high": value_entry(fmt_price(lt.tip_reference_high)),
        "tip_drawdown": value_entry(fmt_pct(liquidity_tip_canonical_drawdown(lt))),
    }
    r_lv = int(r_fac.level) if r_fac is not None else 0
    if r_lv == 2:
        mark_value_keys(values, {"tip_drawdown"})
    return {"r_level": breakdown_level_suffix(r_fac), "values": values}


def _default_value(value: str = "—", *, hit: bool = False) -> dict[str, object]:
    row: dict[str, object] = {"value": value}
    if hit:
        row["hit"] = True
    return row


def _default_r_section() -> dict[str, Any]:
    return {
        "r_level": "—",
        "values": {
            "last_close": _default_value(),
            "tip_reference_high": _default_value(),
            "tip_drawdown": _default_value(),
        },
    }


def build_fixed_r_section(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> dict[str, Any]:
    return build_r_section(fc, bundle, price_symbols) or _default_r_section()
