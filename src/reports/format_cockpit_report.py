"""
Cockpit 計器レポートのテンプレートレンダリング。

責務: データ取得とフォーマット後の値のみ渡す。表示文言はテンプレートに記載。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from reports.format_fc_signal import build_reason, get_raw_metrics
from reports._render import render

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import SignalBundle

MODE_STR = {0: "Boost", 1: "Cruise", 2: "Emergency"}
COCKPIT_TEMPLATE = "cockpit_report.txt"


async def build_fc_report_context(
    fc: "FlightController",
    symbols: list[str],
    now_utc: str,
    bundle: Optional["SignalBundle"] = None,
) -> dict[str, Any]:
    """
    FlightController 計器レポート用のテンプレートコンテキストを組み立てる。
    フォーマット後の値のみ渡し、表示文言はテンプレート側で組み立てる。
    bundle を渡すと復帰 x/N が bundle から算出される。
    """
    signal = await fc.get_flight_controller_signal(bundle)
    mapping = fc.mapping
    symbol_blocks: list[dict[str, Any]] = []
    for sym in symbols:
        sig = signal.by_symbol.get(sym)
        if sig is None:
            continue
        m = get_raw_metrics(mapping, sym)
        reason = build_reason(sig.icl, signal.scl, signal.lcl)
        symbol_blocks.append({
            "symbol": sym,
            "mode": MODE_STR.get(sig.throttle_level, "?"),
            "throttle_level": sig.throttle_level,
            "reason": reason,
            "is_critical": sig.is_critical,
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
    bundle: Optional["SignalBundle"] = None,
) -> str:
    """
    Cockpit 計器レポート文字列をテンプレートで生成する。

    :param fc: update_all 済みの FlightController。
    :param symbols: 銘柄リスト。
    :param now_utc: 取得時刻（UTC 文字列）。
    :param template_name: テンプレートファイル名。
    :param bundle: 未指定可。渡すと復帰 x/N を bundle から算出。
    :return: レポート文字列。
    """
    context = await build_fc_report_context(fc, symbols, now_utc, bundle)
    return render(template_name, context)
