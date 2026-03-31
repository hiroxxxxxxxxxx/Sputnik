"""
Telegram Daily Flight Log 用テキストフォーマット。

責務: データ取得・因子の解釈・値のフォーマット（level→"0"/"1", 価格→文字列など）のみ行う。
表示文言（見出し・表形式・区切り）はテンプレートに記載し、Py はフォーマット後の値のみ渡す。
定義書「4-2」「0-1-Ⅲ」参照。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from avionics.data.futures_micro_equiv import (
    engine_symbol_to_micro_notional_label,
    micro_equivalent_net_gc_family,
    micro_equivalent_net_nq_family,
)
from cockpit.mode import MODE_STR
from engines.blueprint import PART_NAMES
from reports._render import render

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.flight_controller_signal import FlightControllerSignal
    from avionics.data.factor_mapping import EngineFactorMapping
    from avionics.data.raw_types import RawCapitalSnapshot
    from avionics.data.signals import AltitudeRegime, SignalBundle

LEVEL_STR = {0: "0", 1: "1", 2: "2"}

_DEFAULT_TEMPLATE = "daily_flight_log.txt"


def _build_position_rows(
    symbols: list[str],
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, float]]:
    """先物行・オプション行と銘柄別先物ネットを返す。"""
    if not positions_detail:
        return [], [], {}
    futures_rows: list[dict[str, str]] = []
    options_rows: list[dict[str, str]] = []
    futures_actual_net: dict[str, float] = {}
    for sym in symbols:
        detail = positions_detail.get(sym)
        if detail is None:
            continue
        fut = detail.get("futures", {})
        opt = detail.get("options", {})
        futures_rows.append(
            {
                "symbol": sym,
                "nq_buy": f"{float(fut.get('nq_buy', 0.0)):.0f}",
                "nq_sell": f"{float(fut.get('nq_sell', 0.0)):.0f}",
                "mnq_buy": f"{float(fut.get('mnq_buy', 0.0)):.0f}",
                "mnq_sell": f"{float(fut.get('mnq_sell', 0.0)):.0f}",
                "gc_buy": f"{float(fut.get('gc_buy', 0.0)):.0f}",
                "gc_sell": f"{float(fut.get('gc_sell', 0.0)):.0f}",
                "mgc_buy": f"{float(fut.get('mgc_buy', 0.0)):.0f}",
                "mgc_sell": f"{float(fut.get('mgc_sell', 0.0)):.0f}",
            }
        )
        if sym == "NQ":
            futures_actual_net[sym] = micro_equivalent_net_nq_family(fut)
        elif sym == "GC":
            futures_actual_net[sym] = micro_equivalent_net_gc_family(fut)
        options_rows.append(
            {
                "symbol": sym,
                "nq_call_buy": f"{float(opt.get('nq_call_buy', 0.0)):.0f}",
                "nq_call_sell": f"{float(opt.get('nq_call_sell', 0.0)):.0f}",
                "nq_put_buy": f"{float(opt.get('nq_put_buy', 0.0)):.0f}",
                "nq_put_sell": f"{float(opt.get('nq_put_sell', 0.0)):.0f}",
                "mnq_call_buy": f"{float(opt.get('mnq_call_buy', 0.0)):.0f}",
                "mnq_call_sell": f"{float(opt.get('mnq_call_sell', 0.0)):.0f}",
                "mnq_put_buy": f"{float(opt.get('mnq_put_buy', 0.0)):.0f}",
                "mnq_put_sell": f"{float(opt.get('mnq_put_sell', 0.0)):.0f}",
                "gc_call_buy": f"{float(opt.get('gc_call_buy', 0.0)):.0f}",
                "gc_call_sell": f"{float(opt.get('gc_call_sell', 0.0)):.0f}",
                "gc_put_buy": f"{float(opt.get('gc_put_buy', 0.0)):.0f}",
                "gc_put_sell": f"{float(opt.get('gc_put_sell', 0.0)):.0f}",
                "mgc_call_buy": f"{float(opt.get('mgc_call_buy', 0.0)):.0f}",
                "mgc_call_sell": f"{float(opt.get('mgc_call_sell', 0.0)):.0f}",
                "mgc_put_buy": f"{float(opt.get('mgc_put_buy', 0.0)):.0f}",
                "mgc_put_sell": f"{float(opt.get('mgc_put_sell', 0.0)):.0f}",
            }
        )
    return futures_rows, options_rows, futures_actual_net


def _build_futures_target_rows(
    symbols: list[str],
    futures_actual_net: dict[str, float],
    target_futures_by_symbol: Optional[dict[str, dict[str, float]]],
) -> list[dict[str, str]]:
    """先物の target / actual_net / delta 行を返す（銘柄ごとの Part 合計 target）。"""
    if target_futures_by_symbol is None:
        return []
    rows: list[dict[str, str]] = []
    for sym in symbols:
        if sym not in ("NQ", "GC"):
            continue
        parts = target_futures_by_symbol.get(sym)
        if parts is None:
            raise ValueError(f"target_futures missing engine symbol: {sym}")
        missing = [p for p in PART_NAMES if p not in parts]
        if missing:
            raise ValueError(f"target_futures missing part rows for {sym}: {missing}")
        target_total = sum(float(parts[p]) for p in PART_NAMES)
        actual_net = float(futures_actual_net.get(sym, 0.0))
        delta = target_total - actual_net
        rows.append(
            {
                "symbol": sym,
                "micro_label": engine_symbol_to_micro_notional_label(sym),
                "target": f"{target_total:.0f}",
                "actual": f"{actual_net:.0f}",
                "delta": f"{delta:.0f}",
            }
        )
    return rows


def _build_icl_sections(
    symbols: list[str],
    signal: "FlightControllerSignal",
    bundle: "SignalBundle",
    mapping: "EngineFactorMapping",
    *,
    altitude: "AltitudeRegime",
) -> list[dict[str, Any]]:
    """銘柄別 ICL セクション（P,V,C/R の因子行付き）を組み立てる。定義書 4-2-1-3/4-2-1-4 参照。"""
    _icl_ids = ("1-A", "1-B")
    sections: list[dict[str, Any]] = []

    c_val = "—"
    if bundle.liquidity_credit_hyg:
        c_val = "Below SMA20" if bundle.liquidity_credit_hyg.below_sma20 else "Above SMA20"
    r_val = "—"
    if bundle.liquidity_tip and bundle.liquidity_tip.tip_drawdown_from_high is not None:
        r_val = f"{bundle.liquidity_tip.tip_drawdown_from_high * 100:.1f}%"

    for idx, sym in enumerate(symbols):
        if sym not in ("NQ", "GC"):
            continue
        m = signal.get_factor_levels(sym)
        p_lv, v_lv, c_lv, r_lv = m["P"], m["V"], m["C"], m["R"]
        icl_level = signal.nq_icl if sym == "NQ" else signal.gc_icl
        section_id = _icl_ids[idx] if idx < len(_icl_ids) else str(idx + 1)

        ps = bundle.price_signals.get(sym)
        vs = bundle.volatility_signals.get(sym)
        price_str = f"{ps.last_close:,.2f}" if ps else "—"
        p_trend = ps.trend if ps else "—"
        sym_vol = f"{vs.index_value:.1f}" if vs else "—"
        rec = mapping.get_recovery_progress(sym, bundle, altitude=altitude)

        if sym == "NQ":
            icl_level = max(int(icl_level), int(p_lv), int(v_lv), int(c_lv))
            rows = [
                {"factor": "P", "lv": LEVEL_STR.get(p_lv, "?"), "value": f"{price_str} / {p_trend}", "recovery": rec.get("P", "")},
                {"factor": "V", "lv": LEVEL_STR.get(v_lv, "?"), "value": sym_vol, "recovery": rec.get("V", "")},
                {"factor": "C", "lv": LEVEL_STR.get(c_lv, "?"), "value": c_val, "recovery": rec.get("C", "")},
            ]
        else:
            icl_level = max(int(icl_level), int(p_lv), int(v_lv), int(r_lv))
            rows = [
                {"factor": "P", "lv": LEVEL_STR.get(p_lv, "?"), "value": f"{price_str} / {p_trend}", "recovery": rec.get("P", "")},
                {"factor": "V", "lv": LEVEL_STR.get(v_lv, "?"), "value": sym_vol, "recovery": rec.get("V", "")},
                {"factor": "R", "lv": LEVEL_STR.get(r_lv, "?"), "value": r_val, "recovery": rec.get("R", "")},
            ]
        sections.append({"section_id": section_id, "symbol": sym, "level": LEVEL_STR.get(icl_level, "?"), "rows": rows})
    return sections


def _build_capital_lines(
    capital_snapshot: Optional["RawCapitalSnapshot"],
) -> tuple[str, str]:
    """NLV / Cash Buffer のテンプレート行を返す。"""
    if capital_snapshot:
        nlv_line = f"NLV: ${capital_snapshot.nlv:,.0f}  /  ExcessLiq: ${(capital_snapshot.nlv - capital_snapshot.mm) / 1000:.0f}k"
        cash_buffer_line = "Cash Buffer: (🟢 安定)"
    else:
        nlv_line = "NLV: —  /  ExcessLiq: —"
        cash_buffer_line = ""
    return nlv_line, cash_buffer_line


def _build_scl_lcl_rows(
    signal: "FlightControllerSignal",
    bundle: "SignalBundle",
    mapping: "EngineFactorMapping",
    symbols: list[str],
    *,
    altitude: "AltitudeRegime",
) -> tuple[str, list[dict[str, Any]], str, list[dict[str, Any]]]:
    """SCL / LCL セクションの level 文字列と行データを返す。"""
    scl_value = "—"
    if symbols:
        parts = [f"{sym} {ps.trend}" for sym in symbols if (ps := bundle.price_signals.get(sym))]
        scl_value = " x ".join(parts) if parts else "—"

    u_lv = s_lv = 0
    first_sig_recovery: dict[str, str] = {}
    if symbols and symbols[0] in ("NQ", "GC"):
        m0 = signal.get_factor_levels(symbols[0])
        u_lv = int(m0.get("U", 0))
        s_lv = int(m0.get("S", 0))
        first_sig_recovery = mapping.get_recovery_progress(symbols[0], bundle, altitude=altitude)

    cap = bundle.capital_signals
    u_pct = f"{cap.mm_over_nlv * 100:.1f}" if cap else "0.0"
    s_val = f"{cap.span_ratio:.2f}" if cap else "1.00"

    scl_level = LEVEL_STR.get(signal.scl, "?")
    scl_rows = [{"factor": "T", "lv": LEVEL_STR.get(signal.scl, "?"), "value": scl_value, "recovery": first_sig_recovery.get("T", "")}]

    lcl_level = LEVEL_STR.get(max(int(u_lv), int(s_lv)), "?")
    lcl_rows = [
        {"factor": "U", "lv": LEVEL_STR.get(u_lv, "?"), "value": f"{u_pct}% (C1:40% C2:50%)", "recovery": first_sig_recovery.get("U", "")},
        {"factor": "S", "lv": LEVEL_STR.get(s_lv, "?"), "value": f"{s_val} (S1:1.1 S2:1.3)", "recovery": first_sig_recovery.get("S", "")},
    ]
    return scl_level, scl_rows, lcl_level, lcl_rows


async def _build_daily_flight_log_context(
    fc: "FlightController",
    symbols: list[str],
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]] = None,
    target_futures_by_symbol: Optional[dict[str, dict[str, float]]] = None,
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    """FlightController から Daily Flight Log 用のテンプレートコンテキストを組み立てる。"""
    bundle = fc.get_last_bundle()
    if bundle is None:
        raise ValueError("_build_daily_flight_log_context requires fc.refresh() to have been called first")
    altitude = fc.last_altitude_regime
    if altitude is None:
        raise ValueError("_build_daily_flight_log_context requires fc.refresh() or fc.apply_all with altitude")
    capital_snapshot = fc.get_last_capital_snapshot()
    d = as_of or date.today()

    signal = await fc.get_flight_controller_signal()
    worst_level = 0
    for sym in symbols:
        if sym in ("NQ", "GC"):
            worst_level = max(worst_level, signal.throttle_level(sym))

    mapping = fc.mapping
    icl_sections = _build_icl_sections(symbols, signal, bundle, mapping, altitude=altitude)
    nlv_line, cash_buffer_line = _build_capital_lines(capital_snapshot)
    scl_level, scl_rows, lcl_level, lcl_rows = _build_scl_lcl_rows(
        signal, bundle, mapping, symbols, altitude=altitude
    )
    futures_rows, options_rows, futures_actual_net = _build_position_rows(
        symbols, positions_detail
    )
    futures_target_rows = _build_futures_target_rows(
        symbols, futures_actual_net, target_futures_by_symbol
    )

    return {
        "date_iso": d.isoformat(),
        "mode": MODE_STR.get(worst_level, "?"),
        "worst_level": str(worst_level),
        "icl_sections": icl_sections,
        "scl_level": scl_level,
        "scl_rows": scl_rows,
        "lcl_level": lcl_level,
        "lcl_rows": lcl_rows,
        "futures_rows": futures_rows,
        "futures_target_rows": futures_target_rows,
        "options_rows": options_rows,
        "nlv_line": nlv_line,
        "cash_buffer_line": cash_buffer_line,
        "maintenance_lines": ["カレンダー連携は未実装のためスキップ"],
    }


async def format_daily_report(
    fc: "FlightController",
    symbols: list[str],
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]] = None,
    target_futures_by_symbol: Optional[dict[str, dict[str, float]]] = None,
    as_of: Optional[date] = None,
    template_name: str = _DEFAULT_TEMPLATE,
) -> str:
    """
    FlightController から Daily Flight Log 形式のレポート文字列を生成する。
    bundle と capital_snapshot は fc から取得する（refresh 済みの FC を渡すこと）。

    :param fc: refresh 済みの FlightController。
    :param symbols: 銘柄リスト（例: ["NQ", "GC"]）。
    :param positions_detail: 銘柄別ポジション詳細。
        futures は nq_buy/nq_sell, mnq_*, gc_*, mgc_*（オプションは call_buy 等）。
    :param target_futures_by_symbol: DB target_futures（**MNQ/MGC 相当枚数**。内部キーは NQ/GC）。
    :param as_of: 基準日。未指定なら date.today()。
    :param template_name: 使用するテンプレートファイル名。
    :return: Telegram 送信用のテキスト。
    """
    context = await _build_daily_flight_log_context(
        fc,
        symbols,
        positions_detail=positions_detail,
        target_futures_by_symbol=target_futures_by_symbol,
        as_of=as_of,
    )
    return render(template_name, context)
