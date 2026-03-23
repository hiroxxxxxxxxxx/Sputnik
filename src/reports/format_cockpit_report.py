"""
Cockpit 計器レポートのテンプレートレンダリング。

責務: データ取得とフォーマット後の値のみ渡す。表示文言はテンプレートに記載。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reports.format_fc_signal import build_reason, get_raw_metrics
from reports._render import render

if TYPE_CHECKING:
    from avionics import FlightController

MODE_STR = {0: "Boost", 1: "Cruise", 2: "Emergency"}
COCKPIT_TEMPLATE = "cockpit_report.txt"


async def build_fc_report_context(
    fc: "FlightController",
    symbols: list[str],
    now_utc: str,
) -> dict[str, Any]:
    """
    FlightController 計器レポート用のテンプレートコンテキストを組み立てる。
    bundle は fc.get_last_bundle() から取得。表示文言はテンプレート側で組み立てる。
    """
    signal = await fc.get_flight_controller_signal()
    symbol_blocks: list[dict[str, Any]] = []
    for sym in symbols:
        if sym not in ("NQ", "GC"):
            continue
        m = get_raw_metrics(signal, sym)
        icl = signal.nq_icl if sym == "NQ" else signal.gc_icl
        reason = build_reason(icl, signal.scl, signal.lcl)
        throttle = signal.throttle_level(sym)
        symbol_blocks.append({
            "symbol": sym,
            "mode": MODE_STR.get(throttle, "?"),
            "throttle_level": throttle,
            "reason": reason,
            "is_critical": signal.any_critical,
            "p": m.get("P", 0),
            "v": m.get("V", 0),
            "c": m.get("C", 0),
            "r": m.get("R", 0),
            "t": m.get("T", 0),
            "u": m.get("U", 0),
            "s": m.get("S", 0),
        })
    return {"now_utc": now_utc, "symbol_blocks": symbol_blocks}


async def format_cockpit_report(
    fc: "FlightController",
    symbols: list[str],
    now_utc: str,
    template_name: str = COCKPIT_TEMPLATE,
) -> str:
    """
    Cockpit 計器レポート文字列をテンプレートで生成する。
    bundle は fc.get_last_bundle() から取得する（refresh 済みの FC を渡すこと）。

    :param fc: refresh 済みの FlightController。
    :param symbols: 銘柄リスト。
    :param now_utc: 取得時刻（UTC 文字列）。
    :param template_name: テンプレートファイル名。
    :return: レポート文字列。
    """
    context = await build_fc_report_context(fc, symbols, now_utc)
    return render(template_name, context)
