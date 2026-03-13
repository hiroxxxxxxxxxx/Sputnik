"""
Telegram Daily Flight Log 用テキストフォーマット。

責務: データ取得・因子の解釈・値のフォーマット（level→"0"/"1", 価格→文字列など）のみ行う。
表示文言（見出し・表形式・区切り）はテンプレートに記載し、Py はフォーマット後の値のみ渡す。
定義書「4-2」「0-1-Ⅲ」参照。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.Instruments.raw_data import RawCapitalSnapshot
    from avionics.Instruments.signals import SignalBundle

from reports._render import render

MODE_STR = {0: "Boost", 1: "Cruise", 2: "Emergency"}
# Level は数値のみ（ICL/SCL/LCL の層で区別するため M/C 接頭辞は廃止）
LEVEL_STR = {0: "0", 1: "1", 2: "2"}

_DEFAULT_TEMPLATE = "daily_flight_log.txt"


def render_daily_flight_log(context: dict[str, Any], template_name: str = _DEFAULT_TEMPLATE) -> str:
    """
    事前に組み立てたコンテキストで Daily Flight Log テンプレートをレンダリングする。

    :param context: テンプレートに渡す変数（date_iso, mode, market_vectors 等）。
    :param template_name: テンプレートファイル名（templates/ 直下）。
    :return: レンダリング済みテキスト。
    """
    return render(template_name, context)


async def build_daily_flight_log_context(
    cockpit: "FlightController",
    bundle: "SignalBundle",
    symbols: list[str],
    capital_snapshot: Optional["RawCapitalSnapshot"] = None,
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    """
    Cockpit と SignalBundle から Daily Flight Log 用のテンプレートコンテキストを組み立てる。

    :param cockpit: update_all 済みの Cockpit。
    :param bundle: Layer 2 の SignalBundle。
    :param symbols: 銘柄リスト（例: ["NQ", "GC"]）。
    :param capital_snapshot: 証拠金 Raw（任意）。あると NLV / ExcessLiq を表示。
    :param as_of: 基準日。未指定なら date.today()。
    :return: render_daily_flight_log に渡す context 辞書。
    """
    d = as_of or date.today()

    worst_level = 0
    for sym in symbols:
        sig = await cockpit.get_flight_controller_signal(sym, bundle)
        worst_level = max(worst_level, sig.throttle_level)
    mode = MODE_STR.get(worst_level, "?")

    p_lv = v_lv = t_lv = 0
    trend_str = "—"
    gap_str = "—"
    vol_str = "—"
    for sym in symbols:
        sig = await cockpit.get_flight_controller_signal(sym, bundle)
        m = sig.raw_metrics
        p_lv = max(p_lv, m.get("P", 0))
        v_lv = max(v_lv, m.get("V", 0))
        t_lv = max(t_lv, m.get("T", 0))
    if symbols:
        ps = bundle.price_signals.get(symbols[0])
        vs = bundle.volatility_signals.get(symbols[0])
        if ps:
            trend_str = ps.trend
            gap_str = f"Gap: {ps.downside_gap*100:.1f}%" if ps.downside_gap != -0.01 else "—"
        if vs:
            vol_str = f"{vs.index_value:.1f}"
    cap = bundle.capital_signals
    u_lv = s_lv = 0
    first_sig_recovery: dict[str, str] = {}
    if symbols:
        first_sig = await cockpit.get_flight_controller_signal(symbols[0], bundle)
        u_lv = first_sig.raw_metrics.get("U", 0)
        s_lv = first_sig.raw_metrics.get("S", 0)
        first_sig_recovery = first_sig.recovery_metrics
    u_pct = f"{cap.mm_over_nlv * 100:.1f}" if cap else "0.0"
    s_val = f"{cap.span_ratio:.2f}" if cap else "1.00"

    if capital_snapshot:
        nlv_line = f"NLV: ${capital_snapshot.nlv:,.0f}  /  ExcessLiq: ${(capital_snapshot.nlv - capital_snapshot.mm) / 1000:.0f}k"
        cash_buffer_line = "Cash Buffer: (🟢 安定)"
    else:
        nlv_line = "NLV: —  /  ExcessLiq: —"
        cash_buffer_line = ""

    # ICL: NQ は P,V,C / GC は P,V,R。定義書 4-2-1-3 / 4-2-1-4 参照。
    _icl_ids = ("1-A", "1-B")
    icl_sections: list[dict[str, Any]] = []
    c_val = "—"
    if bundle.liquidity_credit:
        c_val = "Below SMA20" if bundle.liquidity_credit.below_sma20 else "Above SMA20"
    r_val = "—"
    if bundle.liquidity_tip and bundle.liquidity_tip.tip_drawdown_from_high is not None:
        r_val = f"{bundle.liquidity_tip.tip_drawdown_from_high * 100:.1f}%"
    for idx, sym in enumerate(symbols):
        sig = await cockpit.get_flight_controller_signal(sym, bundle)
        m = sig.raw_metrics
        p_lv = m.get("P", 0)
        v_lv = m.get("V", 0)
        c_lv = m.get("C", 0)
        r_lv = m.get("R", 0)
        section_id = _icl_ids[idx] if idx < len(_icl_ids) else str(idx + 1)
        ps = bundle.price_signals.get(sym)
        vs = bundle.volatility_signals.get(sym)
        price_str = f"{ps.last_close:,.2f}" if ps else "—"
        p_trend = ps.trend if ps else "—"
        sym_vol = f"{vs.index_value:.1f}" if vs else "—"
        rec = sig.recovery_metrics
        if sym == "NQ":
            icl_level = max(p_lv, v_lv, c_lv)
            rows = [
                {"factor": "P", "lv": LEVEL_STR.get(p_lv, "?"), "value": f"{price_str} / {p_trend}", "recovery": rec.get("P", "")},
                {"factor": "V", "lv": LEVEL_STR.get(v_lv, "?"), "value": sym_vol, "recovery": rec.get("V", "")},
                {"factor": "C", "lv": LEVEL_STR.get(c_lv, "?"), "value": c_val, "recovery": rec.get("C", "")},
            ]
        else:
            icl_level = max(p_lv, v_lv, r_lv)
            rows = [
                {"factor": "P", "lv": LEVEL_STR.get(p_lv, "?"), "value": f"{price_str} / {p_trend}", "recovery": rec.get("P", "")},
                {"factor": "V", "lv": LEVEL_STR.get(v_lv, "?"), "value": sym_vol, "recovery": rec.get("V", "")},
                {"factor": "R", "lv": LEVEL_STR.get(r_lv, "?"), "value": r_val, "recovery": rec.get("R", "")},
            ]
        icl_sections.append({"section_id": section_id, "symbol": sym, "level": LEVEL_STR.get(icl_level, "?"), "rows": rows})

    scl_level = LEVEL_STR.get(t_lv, "?")
    scl_rows = [{"factor": "T", "lv": LEVEL_STR.get(t_lv, "?"), "value": f"Sync (MNQ/MGC) / {trend_str}", "recovery": first_sig_recovery.get("T", "")}]

    lcl_level = LEVEL_STR.get(max(u_lv, s_lv), "?")
    lcl_rows = [
        {"factor": "U", "lv": LEVEL_STR.get(u_lv, "?"), "value": f"{u_pct}% (C1:40% C2:50%)", "recovery": first_sig_recovery.get("U", "")},
        {"factor": "S", "lv": LEVEL_STR.get(s_lv, "?"), "value": f"{s_val} (S1:1.1 S2:1.3)", "recovery": first_sig_recovery.get("S", "")},
    ]

    maintenance_lines = ["カレンダー連携は未実装のためスキップ"]

    return {
        "date_iso": d.isoformat(),
        "mode": mode,
        "worst_level": str(worst_level),
        "icl_sections": icl_sections,
        "scl_level": scl_level,
        "scl_rows": scl_rows,
        "lcl_level": lcl_level,
        "lcl_rows": lcl_rows,
        "nlv_line": nlv_line,
        "cash_buffer_line": cash_buffer_line,
        "maintenance_lines": maintenance_lines,
    }


async def format_daily_flight_log(
    cockpit: "FlightController",
    bundle: "SignalBundle",
    symbols: list[str],
    capital_snapshot: Optional["RawCapitalSnapshot"] = None,
    as_of: Optional[date] = None,
    template_name: str = _DEFAULT_TEMPLATE,
) -> str:
    """
    Cockpit と SignalBundle から Daily Flight Log 形式のレポート文字列を生成する。
    レイアウトはテンプレート（templates/daily_flight_log.txt）で管理する。

    :param cockpit: update_all 済みの Cockpit。
    :param bundle: Layer 2 の SignalBundle。
    :param symbols: 銘柄リスト（例: ["NQ", "GC"]）。
    :param capital_snapshot: 証拠金 Raw（任意）。あると NLV / ExcessLiq を表示。
    :param as_of: 基準日。未指定なら date.today()。
    :param template_name: 使用するテンプレートファイル名。
    :return: Telegram 送信用のテキスト。
    """
    context = await build_daily_flight_log_context(
        cockpit, bundle, symbols, capital_snapshot=capital_snapshot, as_of=as_of
    )
    return render_daily_flight_log(context, template_name=template_name)
