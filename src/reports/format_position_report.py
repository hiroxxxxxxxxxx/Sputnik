"""Telegram position レポートのテンプレートレンダリング。"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from cockpit.mode import BOOST, CRUISE, EMERGENCY, ModeType
from reports._render import render
from reports.position_report_context import build_position_report_context

if TYPE_CHECKING:
    from avionics import FlightController

POSITION_TEMPLATE = "position_report.txt"


def _level_to_mode(level: int) -> ModeType:
    if level >= 2:
        return EMERGENCY
    if level == 1:
        return CRUISE
    return BOOST


async def _build_position_report_context(
    fc: "FlightController",
    symbols: list[str],
    *,
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]] = None,
    target_base_by_symbol: Optional[dict[str, float]] = None,
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    d = as_of or date.today()
    signal = await fc.get_flight_controller_signal()
    modes_by_symbol: dict[str, ModeType] = {}
    for sym in symbols:
        if sym in ("NQ", "GC"):
            modes_by_symbol[sym] = _level_to_mode(signal.throttle_level(sym))
    position_ctx = build_position_report_context(
        symbols,
        positions_detail=positions_detail,
        target_base_by_symbol=target_base_by_symbol,
        modes_by_symbol=modes_by_symbol,
        altitude=str(fc.last_altitude_regime or "mid"),
    )
    return {
        "date_iso": d.isoformat(),
        "symbols": position_ctx["symbols"],
        "futures_rows": position_ctx["futures_rows"],
        "options_rows": position_ctx["options_rows"],
        "futures_target_rows": position_ctx["futures_target_rows"],
    }


async def format_position_report(
    fc: "FlightController",
    symbols: list[str],
    *,
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]] = None,
    target_base_by_symbol: Optional[dict[str, float]] = None,
    as_of: Optional[date] = None,
    template_name: str = POSITION_TEMPLATE,
) -> str:
    """positions セクションのみのレポートを生成する。"""
    context = await _build_position_report_context(
        fc,
        symbols,
        positions_detail=positions_detail,
        target_base_by_symbol=target_base_by_symbol,
        as_of=as_of,
    )
    return render(template_name, context)
