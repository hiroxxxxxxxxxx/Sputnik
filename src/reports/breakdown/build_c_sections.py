from __future__ import annotations

from typing import TYPE_CHECKING, Any

from avionics.compute import liquidity_credit_canonical_inputs
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


def _credit_values(lc: Any) -> dict[str, dict[str, object]]:
    _, dc = liquidity_credit_canonical_inputs(lc)
    dc_show = dc if dc is not None else lc.daily_change
    return {
        "last_close": value_entry(fmt_price(lc.last_close)),
        "sma20": value_entry(fmt_price(lc.sma20)),
        "sma20_gap": value_entry(fmt_pct(lc.sma20_gap)),
        "daily_change": value_entry(fmt_pct(dc_show)),
    }


def build_c_sections(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> list[dict[str, Any]]:
    from avionics.factors.c_factor import CFactor, c_breakdown_hit_row_keys_from_snapshot

    c_fac = _first_factor_among_symbols(fc, price_symbols, CFactor)
    c_lv = breakdown_level_suffix(c_fac)
    sections: list[dict[str, Any]] = []

    if bundle.liquidity_credit_hyg:
        values = _credit_values(bundle.liquidity_credit_hyg)
        if c_fac is not None and int(c_fac.level) == 2:
            dc_th = float(c_fac.thresholds["daily_change_C2"])
            bs_h, dc_h = liquidity_credit_canonical_inputs(bundle.liquidity_credit_hyg)
            mark_value_keys(values, set(c_breakdown_hit_row_keys_from_snapshot(bs_h, dc_h, dc_th)))
        sections.append({"credit_symbol": "HYG", "c_level": c_lv, "values": values})

    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
    if lc_lqd:
        values = _credit_values(lc_lqd)
        if c_fac is not None and int(c_fac.level) == 2:
            dc_th = float(c_fac.thresholds["daily_change_C2"])
            bs_l, dc_l = liquidity_credit_canonical_inputs(lc_lqd)
            mark_value_keys(values, set(c_breakdown_hit_row_keys_from_snapshot(bs_l, dc_l, dc_th)))
        sections.append({"credit_symbol": "LQD", "c_level": c_lv, "values": values})

    return sections


def _default_value(value: str = "—", *, hit: bool = False) -> dict[str, object]:
    row: dict[str, object] = {"value": value}
    if hit:
        row["hit"] = True
    return row


def _default_credit_section(symbol: str) -> dict[str, Any]:
    return {
        "credit_symbol": symbol,
        "c_level": "—",
        "values": {
            "last_close": _default_value(),
            "sma20": _default_value(),
            "sma20_gap": _default_value(),
            "daily_change": _default_value(),
        },
    }


def build_fixed_c_sections(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> dict[str, dict[str, Any]]:
    by_symbol = {s["credit_symbol"]: s for s in build_c_sections(fc, bundle, price_symbols)}
    return {
        "hyg": by_symbol.get("HYG", _default_credit_section("HYG")),
        "lqd": by_symbol.get("LQD", _default_credit_section("LQD")),
    }
