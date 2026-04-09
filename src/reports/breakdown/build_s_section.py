from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reports.breakdown.common import breakdown_level_suffix, fmt_float_or_na, safe_ratio_text

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import SignalBundle


def _limit_factor(fc: "FlightController", cls: type) -> Any:
    for f in fc.mapping.limit_factors:
        if isinstance(f, cls):
            return f
    return None


def build_s_section(fc: "FlightController", bundle: "SignalBundle") -> dict[str, Any] | None:
    from avionics.factors.s_factor import SFactor

    if not bundle.capital_signals:
        return None
    cs = bundle.capital_signals
    baseline_map = cs.s_baseline_mm_per_lot
    whatif_map = cs.s_whatif_mm_per_lot
    whatif_errors = cs.s_whatif_errors or {}
    syms = sorted(baseline_map.keys()) if baseline_map else sorted(whatif_map.keys()) if whatif_map else []
    has_full_whatif = bool(syms and whatif_map is not None and all(sym in whatif_map for sym in syms))
    whatif_total = sum(float(whatif_map[s]) for s in syms) if has_full_whatif else None
    baseline_total = sum(float(baseline_map[s]) for s in syms if baseline_map and s in baseline_map) if baseline_map is not None and syms else None
    per_symbol = []
    for sym in ("NQ", "GC"):
        w = float(whatif_map[sym]) if whatif_map is not None and sym in whatif_map else None
        b = float(baseline_map[sym]) if baseline_map is not None and sym in baseline_map else None
        per_symbol.append({
            "symbol": sym,
            "whatif": fmt_float_or_na(w),
            "baseline": fmt_float_or_na(b),
            "ratio": safe_ratio_text(w, b),
            "reason": whatif_errors.get(sym),
        })
    return {
        "s_level": breakdown_level_suffix(_limit_factor(fc, SFactor)),
        "span_ratio": f"{cs.span_ratio:.2f}",
        "whatif_total": fmt_float_or_na(whatif_total),
        "baseline_total": fmt_float_or_na(baseline_total),
        "total_ratio": safe_ratio_text(whatif_total, baseline_total),
        "per_symbol": per_symbol,
    }


def _default_s_section() -> dict[str, Any]:
    return {
        "s_level": "—",
        "span_ratio": "N/A",
        "whatif_total": "N/A",
        "baseline_total": "N/A",
        "total_ratio": "N/A",
        "per_symbol": [
            {"symbol": "NQ", "whatif": "N/A", "baseline": "N/A", "ratio": "N/A", "reason": None},
            {"symbol": "GC", "whatif": "N/A", "baseline": "N/A", "ratio": "N/A", "reason": None},
        ],
    }


def build_fixed_s_section(fc: "FlightController", bundle: "SignalBundle") -> dict[str, Any]:
    s_sec = build_s_section(fc, bundle) or _default_s_section()
    by_symbol = {row["symbol"]: row for row in s_sec.get("per_symbol", [])}
    return {
        "s_level": s_sec.get("s_level", "—"),
        "span_ratio": s_sec.get("span_ratio", "N/A"),
        "whatif_total": s_sec.get("whatif_total", "N/A"),
        "baseline_total": s_sec.get("baseline_total", "N/A"),
        "total_ratio": s_sec.get("total_ratio", "N/A"),
        "nq": by_symbol.get("NQ", {"whatif": "N/A", "baseline": "N/A", "ratio": "N/A", "reason": None}),
        "gc": by_symbol.get("GC", {"whatif": "N/A", "baseline": "N/A", "ratio": "N/A", "reason": None}),
    }
