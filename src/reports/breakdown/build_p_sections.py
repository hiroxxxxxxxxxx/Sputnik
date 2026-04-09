from __future__ import annotations

from typing import TYPE_CHECKING, Any

from avionics.compute import price_signals_p_input_tuple
from reports.breakdown.common import (
    breakdown_level_suffix,
    fmt_pct,
    fmt_price,
    mark_value_keys,
    value_entry,
)

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import SignalBundle


def _factor_from_symbol(fc: "FlightController", symbol: str, cls: type) -> Any:
    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, cls):
            return f
    return None


def _price_values(ps: Any) -> dict[str, dict[str, object]]:
    dc, c5, hg, tr, c2 = price_signals_p_input_tuple(ps)
    return {
        "last_close": value_entry(fmt_price(ps.last_close)),
        "sma20": value_entry(fmt_price(ps.sma20)),
        "sma20_gap": value_entry(fmt_pct(ps.sma20_gap)),
        "trend": value_entry(str(tr)),
        "daily_change": value_entry(fmt_pct(dc)),
        "cum2_change": value_entry(fmt_pct(c2)),
        "cum5_change": value_entry(fmt_pct(c5)),
        "high_20": value_entry(fmt_price(ps.high_20)),
        "high_20_gap": value_entry(fmt_pct(hg)),
    }


def _p_reason_hit_keys(reason: str) -> set[str]:
    mapping = {
        "P2_daily": {"daily_change"},
        "P2_cum2": {"cum2_change"},
        "P2_gap_down": {"high_20_gap", "trend"},
        "P1_daily_band": {"daily_change"},
        "P1_cum5_band": {"cum5_change"},
        "P1_gap_band": {"high_20_gap"},
        "P0_calm": set(),
        "P1_default": set(),
    }
    return set(mapping[reason])


def _apply_p_hits(values: dict[str, dict[str, object]], notes: list[str], p_factor: Any, ps: Any) -> None:
    from avionics.factors.p_factor import p_classify_row_with_reason, p_failed_p0_row_keys

    if p_factor is None:
        return
    dc, c5, hg, tr, c2 = price_signals_p_input_tuple(ps)
    if hg is None:
        notes.append("high_20_gap 未取得のため P 分類マークを付けていません。")
        return
    try:
        lvl_snap, rid = p_classify_row_with_reason(p_factor.thresholds, dc, c5, hg, tr, c2)
        if rid != "P0_calm":
            p0_set = set(p_failed_p0_row_keys(p_factor.thresholds, dc, c5, hg, tr))
            mark_value_keys(values, _p_reason_hit_keys(rid) | p0_set)
        if int(p_factor.level) != int(lvl_snap):
            notes.append("表示時点の因子レベルと最新行分類が一致しません（refresh 順序を確認）。")
    except ValueError:
        pass


def build_p_sections(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> list[dict[str, Any]]:
    from avionics.factors.p_factor import PFactor
    from avionics.factors.t_factor import TFactor

    sections: list[dict[str, Any]] = []
    for sym in price_symbols:
        ps = bundle.price_signals[sym]
        values = _price_values(ps)
        notes: list[str] = []
        p_factor = _factor_from_symbol(fc, sym, PFactor)
        t_fac = _factor_from_symbol(fc, sym, TFactor)
        _apply_p_hits(values, notes, p_factor, ps)
        sections.append(
            {
                "symbol": sym,
                "p_level": breakdown_level_suffix(p_factor),
                "t_level": breakdown_level_suffix(t_fac),
                "values": values,
                "notes": notes,
            }
        )
    return sections


def _default_value(value: str = "—", *, hit: bool = False) -> dict[str, object]:
    row: dict[str, object] = {"value": value}
    if hit:
        row["hit"] = True
    return row


def _default_price_section(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "p_level": "—",
        "t_level": "—",
        "values": {
            "last_close": _default_value(),
            "sma20": _default_value(),
            "sma20_gap": _default_value(),
            "trend": _default_value(),
            "daily_change": _default_value(),
            "cum2_change": _default_value(),
            "cum5_change": _default_value(),
            "high_20": _default_value(),
            "high_20_gap": _default_value(),
        },
        "notes": [],
    }


def build_fixed_p_sections(
    fc: "FlightController",
    bundle: "SignalBundle",
    price_symbols: list[str],
) -> dict[str, dict[str, Any]]:
    by_symbol = {s["symbol"]: s for s in build_p_sections(fc, bundle, price_symbols)}
    return {
        "nq": by_symbol.get("NQ", _default_price_section("NQ")),
        "gc": by_symbol.get("GC", _default_price_section("GC")),
    }
