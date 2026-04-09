"""Layer 2 シグナル内訳（breakdown / detail）レポートのテンプレートレンダリング。"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Iterable, Optional

from cockpit.mode import ModeType
from reports._render import render
from reports.breakdown.build_c_sections import build_fixed_c_sections
from reports.breakdown.build_p_sections import build_fixed_p_sections
from reports.breakdown.build_r_section import build_fixed_r_section
from reports.breakdown.build_s_section import build_fixed_s_section
from reports.breakdown.build_t_section import build_fixed_t_section
from reports.breakdown.build_u_section import build_fixed_u_section
from reports.breakdown.build_v_sections import build_fixed_v_sections
from reports.position_report_context import build_position_report_context

if TYPE_CHECKING:
    from avionics import FlightController

BREAKDOWN_TEMPLATE = "breakdown_report.txt"


def _collect_symbols(keys: Iterable[str]) -> list[str]:
    primary = ("NQ", "GC")
    key_set = set(keys)
    symbols = [s for s in primary if s in key_set]
    symbols += sorted(s for s in key_set if s not in primary)
    return symbols


def _build_position_ctx(
    *,
    altitude: str,
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]],
    target_base_by_symbol: Optional[dict[str, float]],
    modes_by_symbol: Optional[dict[str, ModeType]],
) -> dict[str, list[dict[str, object]]]:
    if positions_detail and target_base_by_symbol is not None and modes_by_symbol is not None:
        return build_position_report_context(
            ["NQ", "GC"],
            positions_detail=positions_detail,
            target_base_by_symbol=target_base_by_symbol,
            modes_by_symbol=modes_by_symbol,
            altitude=altitude,
        )
    return {"futures_target_rows": [], "options_rows": []}


def format_breakdown_report(
    fc: "FlightController",
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]] = None,
    target_base_by_symbol: Optional[dict[str, float]] = None,
    modes_by_symbol: Optional[dict[str, ModeType]] = None,
    template_name: str = BREAKDOWN_TEMPLATE,
) -> str:
    bundle = fc.get_last_bundle()
    if bundle is None:
        raise ValueError("format_breakdown_report requires fc.refresh() to have been called first")
    altitude = fc.last_altitude_regime
    if altitude is None:
        raise ValueError("format_breakdown_report requires fc.refresh() so last_altitude_regime is set")

    cap = fc.get_last_capital_snapshot()
    date_iso = cap.as_of.isoformat() if cap and getattr(cap, "as_of", None) else date.today().isoformat()
    price_symbols = _collect_symbols(bundle.price_signals.keys())
    vol_symbols = _collect_symbols(bundle.volatility_signals.keys())

    p_sections = build_fixed_p_sections(fc, bundle, price_symbols)
    v_sections = build_fixed_v_sections(fc, bundle, vol_symbols, altitude=altitude)
    c_sections = build_fixed_c_sections(fc, bundle, price_symbols)
    position_ctx = _build_position_ctx(
        altitude=str(altitude),
        positions_detail=positions_detail,
        target_base_by_symbol=target_base_by_symbol,
        modes_by_symbol=modes_by_symbol,
    )
    context = {
        "date_iso": date_iso,
        "price_nq": p_sections["nq"],
        "price_gc": p_sections["gc"],
        "vol_nq": v_sections["nq"],
        "vol_gc": v_sections["gc"],
        "credit_hyg": c_sections["hyg"],
        "credit_lqd": c_sections["lqd"],
        "r_section": build_fixed_r_section(fc, bundle, price_symbols),
        "t_section": build_fixed_t_section(fc, bundle, price_symbols),
        "u_section": build_fixed_u_section(fc, bundle),
        "s_section": build_fixed_s_section(fc, bundle),
        "pos_futures_target_rows_nq": [r for r in position_ctx["futures_target_rows"] if r.get("symbol") == "NQ"],
        "pos_futures_target_rows_gc": [r for r in position_ctx["futures_target_rows"] if r.get("symbol") == "GC"],
        "pos_options_rows_nq": [r for r in position_ctx["options_rows"] if r.get("symbol") == "NQ"],
        "pos_options_rows_gc": [r for r in position_ctx["options_rows"] if r.get("symbol") == "GC"],
    }
    return render(template_name, context)
