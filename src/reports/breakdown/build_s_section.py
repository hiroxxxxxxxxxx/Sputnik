from __future__ import annotations

import re
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


def _truncate_text(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return f"{text[: max_len - 3]}..."


def _summarize_reason(raw_reason: Any, *, max_len: int = 80) -> str | None:
    if raw_reason in (None, ""):
        return None
    text = str(raw_reason).strip()
    if not text:
        return None

    category = "Error"
    short_message = text
    if "No Trading Permission" in text or "Customer Ineligible" in text:
        category = "PermissionError"
        short_message = "No Trading Permission"
    else:
        api_match = re.search(r"API error:\s*(\d+):\s*([^;]+)", text)
        if api_match:
            category = "ApiError"
            short_message = f"API {api_match.group(1)}: {api_match.group(2).strip()}"
        elif "Timeout" in text:
            category = "TimeoutError"
            short_message = "Request timeout"
        else:
            head = text.split(":", 1)[0].strip()
            if head.endswith("Error"):
                category = head
                short_message = text.split(":", 1)[1].strip() if ":" in text else text

    return _truncate_text(f"{category}: {short_message}", max_len=max_len)


def build_s_section(fc: "FlightController", bundle: "SignalBundle") -> dict[str, Any] | None:
    from avionics.factors.s_factor import SFactor

    if not bundle.capital_signals:
        return None
    cs = bundle.capital_signals
    baseline_map = cs.s_baseline_mm_per_lot
    whatif_map = cs.s_whatif_mm_per_lot
    whatif_errors = cs.s_whatif_errors or {}
    syms = sorted(baseline_map.keys()) if baseline_map else sorted(whatif_map.keys()) if whatif_map else []
    success_symbols = [sym for sym in syms if whatif_map is not None and sym in whatif_map]
    has_any_whatif = bool(success_symbols)
    whatif_total = sum(float(whatif_map[s]) for s in success_symbols) if has_any_whatif else None
    baseline_total = sum(float(baseline_map[s]) for s in syms if baseline_map and s in baseline_map) if baseline_map is not None and syms else None
    success_baseline_total = (
        sum(float(baseline_map[s]) for s in success_symbols if baseline_map and s in baseline_map)
        if baseline_map is not None and success_symbols
        else None
    )
    required_count = len(syms)
    success_count = len(success_symbols)
    if required_count == 0:
        coverage_text = "none 0/0"
    elif success_count == required_count:
        coverage_text = f"full {success_count}/{required_count}"
    else:
        symbols_text = ",".join(success_symbols) if success_symbols else "none"
        coverage_text = f"partial {success_count}/{required_count} ({symbols_text})"
    per_symbol = []
    for sym in ("NQ", "GC"):
        w = float(whatif_map[sym]) if whatif_map is not None and sym in whatif_map else None
        b = float(baseline_map[sym]) if baseline_map is not None and sym in baseline_map else None
        per_symbol.append({
            "symbol": sym,
            "whatif": fmt_float_or_na(w),
            "baseline": fmt_float_or_na(b),
            "ratio": safe_ratio_text(w, b),
            "reason": _summarize_reason(whatif_errors.get(sym), max_len=80),
        })
    return {
        "s_level": breakdown_level_suffix(_limit_factor(fc, SFactor)),
        "span_ratio": f"{cs.span_ratio:.2f}",
        "whatif_total": fmt_float_or_na(whatif_total),
        "baseline_total": fmt_float_or_na(baseline_total),
        "total_ratio": safe_ratio_text(whatif_total, success_baseline_total),
        "required_symbols": syms,
        "success_symbols": success_symbols,
        "is_partial": bool(required_count and success_count < required_count),
        "coverage_text": coverage_text,
        "per_symbol": per_symbol,
    }


def _default_s_section() -> dict[str, Any]:
    return {
        "s_level": "—",
        "span_ratio": "N/A",
        "whatif_total": "N/A",
        "baseline_total": "N/A",
        "total_ratio": "N/A",
        "required_symbols": [],
        "success_symbols": [],
        "is_partial": False,
        "coverage_text": "none 0/0",
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
        "coverage_text": s_sec.get("coverage_text", "none 0/0"),
        "nq": by_symbol.get("NQ", {"whatif": "N/A", "baseline": "N/A", "ratio": "N/A", "reason": None}),
        "gc": by_symbol.get("GC", {"whatif": "N/A", "baseline": "N/A", "ratio": "N/A", "reason": None}),
    }
