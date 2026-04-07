"""
Layer 2 シグナル内訳（breakdown / detail）レポートのテンプレートレンダリング。

責務: フォーマット後の値のみ渡す。表示文言・レイアウトはテンプレートに記載。
`daily_report.txt` と同様の区切り線・セクション見出しで読みやすくする。
bundle は FC から get_last_bundle() で取得する。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from cockpit.mode import ModeType
from reports._render import render
from reports.position_report_context import build_position_report_context

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import AltitudeRegime, LiquiditySignals, SignalBundle

BREAKDOWN_TEMPLATE = "breakdown_report.txt"

_PT_IDS = ("1-A", "1-B")
_V_IDS = ("2-A", "2-B")
_C_IDS = ("3-A", "3-B")

_BREAKDOWN_LEVEL_STR = {0: "0", 1: "1", 2: "2"}

# breakdown 末尾に一度だけ出す（全因子共通の ★ 説明）
BREAKDOWN_HIT_LEGEND = "※ ★ = 因子判定の決定枝に関係する入力行を示す。"


def _kv(label: str, value: str, *, row_key: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"label": label, "value": value, "hit": ""}
    if row_key is not None:
        row["row_key"] = row_key
    return row


P_BREAKDOWN_HIT_MARKER = "★"


def _fmt_price(value: float | None) -> str:
    return "—" if value is None else f"{float(value):,.2f}"


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{float(value) * 100:.2f}%"


def _fmt_float_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{float(value):.2f}"


def _safe_ratio_text(numerator: float | None, denominator: float | None) -> str:
    if numerator is None or denominator is None or denominator <= 0:
        return "N/A"
    return f"{float(numerator / denominator):.2f}"


def _v_confirm_days(
    fc: "FlightController",
    symbol: str,
    *,
    altitude: "AltitudeRegime",
) -> tuple[int | None, int | None]:
    """V因子の confirm_days（V1/V2）を取得する。見つからない場合は例外。"""
    from avionics.factors.v_factor import VFactor

    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, VFactor):
            th = f._get_thresholds(altitude)
            return (int(th["V1_confirm_days"]), int(th["V2_confirm_days"]))
    raise ValueError(f"VFactor not found for symbol={symbol!r} in FlightController mapping")


def _v_factor_level(fc: "FlightController", symbol: str) -> int:
    """銘柄に紐づく V 因子の現在レベル（0/1/2）を返す。"""
    from avionics.factors.v_factor import VFactor

    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, VFactor):
            return int(f.level)
    raise ValueError(f"VFactor not found for symbol={symbol!r} in FlightController mapping")


def _factor_from_symbol(fc: "FlightController", symbol: str, cls: type) -> Any:
    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, cls):
            return f
    return None


def _first_factor_among_symbols(
    fc: "FlightController",
    symbols: list[str],
    cls: type,
) -> Any:
    for sym in symbols:
        f = _factor_from_symbol(fc, sym, cls)
        if f is not None:
            return f
    return None


def _limit_factor(fc: "FlightController", cls: type) -> Any:
    for f in fc.mapping.limit_factors:
        if isinstance(f, cls):
            return f
    return None


def _breakdown_level_suffix(fac: Any) -> str:
    if fac is None:
        return "—"
    return _BREAKDOWN_LEVEL_STR.get(int(fac.level), "?")


def _fmt_progress(x: int, total: int) -> str:
    if total <= 0:
        raise ValueError(f"confirm_days must be positive, got {total}")
    return f"{x}/{total}日目"


def _liquidity_credit_section(
    section_id: str,
    title: str,
    lc: "LiquiditySignals",
) -> dict[str, Any]:
    """C（credit）1本ぶん: スナップショット行のみ。"""
    below_txt = "—" if lc.below_sma20 is None else ("Below SMA20" if lc.below_sma20 else "Above SMA20")
    dc_txt = _fmt_pct(lc.daily_change)
    close_txt = _fmt_price(lc.last_close)
    sma_txt = _fmt_price(lc.sma20)
    sma_gap_txt = _fmt_pct(lc.sma20_gap)
    rows = [
        _kv("終値", close_txt),
        _kv("SMA20", sma_txt),
        _kv("SMA20乖離率", sma_gap_txt),
        _kv("日次変化率", dc_txt),
    ]
    return {
        "section_id": section_id,
        "title": title,
        "rows": rows,
    }


def _build_breakdown_report_context(
    fc: "FlightController",
    bundle: "SignalBundle",
    *,
    altitude: "AltitudeRegime",
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]] = None,
    target_base_by_symbol: Optional[dict[str, float]] = None,
    modes_by_symbol: Optional[dict[str, ModeType]] = None,
) -> dict[str, Any]:
    """
    Layer 2 シグナル内訳用のテンプレートコンテキストを組み立てる。
    """
    cap = fc.get_last_capital_snapshot()
    date_iso = cap.as_of.isoformat() if cap and getattr(cap, "as_of", None) else date.today().isoformat()

    price_symbols = [s for s in ("NQ", "GC") if s in bundle.price_signals]
    price_symbols += sorted(s for s in bundle.price_signals if s not in ("NQ", "GC"))

    from avionics.factors.p_factor import PFactor, p_classify_row_hit_row_keys, p_classify_row_with_reason
    from avionics.factors.t_factor import TFactor

    price_sections: list[dict[str, Any]] = []
    for idx, sym in enumerate(price_symbols):
        ps = bundle.price_signals[sym]
        sid = _PT_IDS[idx] if idx < len(_PT_IDS) else str(idx + 1)
        settlement_txt = _fmt_price(ps.last_close)
        sma20_txt = _fmt_price(ps.sma20)
        sma20_gap_txt = _fmt_pct(ps.sma20_gap)
        high20_txt = _fmt_price(ps.high_20)
        high20_gap_txt = _fmt_pct(ps.high_20_gap)
        rows: list[dict[str, Any]] = [
            _kv("清算値", settlement_txt),
            _kv("20SMA", sma20_txt),
            _kv("20SMA乖離率", sma20_gap_txt),
            _kv("トレンド", ps.trend, row_key="trend"),
            _kv("日次変化率", _fmt_pct(ps.daily_change), row_key="daily_change"),
            _kv("2日累積変動率", _fmt_pct(ps.cum2_change), row_key="cum2_change"),
            _kv("5日累積変動率", _fmt_pct(ps.cum5_change), row_key="cum5_change"),
            _kv("20日高値", high20_txt),
            _kv("20日高値乖離率", high20_gap_txt, row_key="high_20_gap"),
        ]
        p_factor = _factor_from_symbol(fc, sym, PFactor)
        t_fac = _factor_from_symbol(fc, sym, TFactor)
        sec_title = (
            f"P/T 入力 <{sym}> [ P={_breakdown_level_suffix(p_factor)} "
            f"T={_breakdown_level_suffix(t_fac)} ]"
        )
        if p_factor is not None and ps.high_20_gap is not None:
            try:
                latest = p_factor.latest_price_daily_row(ps)
                _, dc, c5, hg, tr, c2 = (
                    latest[0],
                    latest[1],
                    latest[2],
                    latest[3],
                    latest[4],
                    latest[5] if len(latest) > 5 else None,
                )
                lvl_snap, rid = p_classify_row_with_reason(
                    p_factor.thresholds, dc, c5, hg, tr, c2
                )
                hit_keys = p_classify_row_hit_row_keys(rid)
                for r in rows:
                    rk = r.get("row_key")
                    if rk and rk in hit_keys:
                        r["hit"] = P_BREAKDOWN_HIT_MARKER
                eff = int(p_factor.level)
                if eff != lvl_snap:
                    rows.append(
                        _kv(
                            "P 注釈",
                            "表示時点の因子レベルと最新行分類が一致しません（refresh 順序を確認）。",
                        )
                    )
            except ValueError:
                pass
        elif p_factor is not None:
            rows.append(
                _kv(
                    "P 注釈",
                    "high_20_gap 未取得のため P 分類マークを付けていません。",
                )
            )
        for r in rows:
            r.pop("row_key", None)
        price_sections.append({
            "section_id": sid,
            "title": sec_title,
            "rows": rows,
        })

    vol_symbols = [s for s in ("NQ", "GC") if s in bundle.volatility_signals]
    vol_symbols += sorted(s for s in bundle.volatility_signals if s not in ("NQ", "GC"))

    volatility_sections: list[dict[str, Any]] = []
    for idx, sym in enumerate(vol_symbols):
        vs = bundle.volatility_signals[sym]
        v1_days, v2_days = _v_confirm_days(fc, sym, altitude=altitude)
        v_level = _v_factor_level(fc, sym)
        sid = _V_IDS[idx] if idx < len(_V_IDS) else str(idx + 10)
        rows = [
            _kv("ボラ指数 (VXN/GVZ 相当)", f"{vs.index_value:.2f}"),
            _kv("20日高値", _fmt_price(vs.high_20)),
        ]
        if v_level == 1:
            x1 = min(vs.recovery_confirm_satisfied_days_v1_off, v1_days)
            rows.append(
                _kv("V1→V0復帰判定", _fmt_progress(x1, v1_days)),
            )
            if vs.recovery_confirm_satisfied_days_v1_off >= v1_days:
                knock_txt = "はい" if vs.v1_to_v0_knock_in_ok else "いいえ"
                rows.extend(
                    [
                        _kv(" ・ノックイン成立", knock_txt),
                        _kv(" ・ノックイン判定時刻", vs.knock_in_bar_end or "—"),
                    ]
                )
        elif v_level == 2:
            x2 = min(vs.recovery_confirm_satisfied_days_v2_off, v2_days)
            rows.append(
                _kv("V2→V1復帰判定", _fmt_progress(x2, v2_days)),
            )
        volatility_sections.append({
            "section_id": sid,
            "title": f"V 入力 <{sym}> [ V={_BREAKDOWN_LEVEL_STR[v_level]} ]",
            "rows": rows,
        })

    from avionics.factors.c_factor import CFactor
    from avionics.factors.r_factor import RFactor
    from avionics.factors.s_factor import SFactor
    from avionics.factors.u_factor import UFactor

    c_lv = _breakdown_level_suffix(_first_factor_among_symbols(fc, price_symbols, CFactor))

    credit_sections: list[dict[str, Any]] = []
    if bundle.liquidity_credit_hyg:
        credit_sections.append(
            _liquidity_credit_section(
                _C_IDS[0],
                f"C（HYG） [ C={c_lv} ]",
                bundle.liquidity_credit_hyg,
            )
        )
    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
    if lc_lqd:
        credit_sections.append(
            _liquidity_credit_section(
                _C_IDS[1] if len(_C_IDS) > 1 else "3-B",
                f"C（LQD） [ C={c_lv} ]",
                lc_lqd,
            )
        )

    r_fac = _first_factor_among_symbols(fc, price_symbols, RFactor)
    r_lv = _breakdown_level_suffix(r_fac)

    r_section: dict[str, Any] | None = None
    if bundle.liquidity_tip:
        lt = bundle.liquidity_tip
        dd_txt = _fmt_pct(lt.tip_drawdown_from_high)
        close_txt = _fmt_price(lt.last_close)
        ref_high_txt = _fmt_price(lt.tip_reference_high)
        r_section = {
            "title": f"[4] R（TIP） [ R={r_lv} ]",
            "rows": [
                _kv("終値", close_txt),
                _kv("20日高値", ref_high_txt),
                _kv("20日高値乖離率", dd_txt),
            ],
        }

    u_section: dict[str, Any] | None = None
    s_section: dict[str, Any] | None = None
    if bundle.capital_signals:
        cs = bundle.capital_signals
        u_rows = [
            _kv("MM/NLV", f"{cs.mm_over_nlv:.2f} ({cs.mm_over_nlv * 100:.2f}%)"),
        ]
        s_rows = [
            _kv("SPAN 比 (span_ratio)", f"{cs.span_ratio:.2f}"),
        ]
        baseline_map = cs.s_baseline_mm_per_lot
        whatif_map = cs.s_whatif_mm_per_lot
        whatif_errors = cs.s_whatif_errors or {}
        syms = sorted(baseline_map.keys()) if baseline_map else []
        if not syms:
            syms = sorted(whatif_map.keys()) if whatif_map else []

        has_full_whatif = bool(
            syms
            and whatif_map is not None
            and all(sym in whatif_map for sym in syms)
        )
        whatif_total = (
            sum(float(whatif_map[s]) for s in syms)  # type: ignore[index]
            if has_full_whatif
            else None
        )
        baseline_total = (
            sum(float(baseline_map[s]) for s in syms if baseline_map and s in baseline_map)
            if baseline_map is not None and syms
            else None
        )
        s_rows.extend(
            [
                _kv("S whatIf total", _fmt_float_or_na(whatif_total)),
                _kv("S baseline total", _fmt_float_or_na(baseline_total)),
                _kv("S total ratio (whatIf/base)", _safe_ratio_text(whatif_total, baseline_total)),
            ]
        )

        for sym in ("NQ", "GC"):
            w = (
                float(whatif_map[sym])
                if whatif_map is not None and sym in whatif_map
                else None
            )
            b = (
                float(baseline_map[sym])
                if baseline_map is not None and sym in baseline_map
                else None
            )
            s_rows.append(
                _kv(
                    f"S {sym} (whatIf/base/ratio)",
                    f"{_fmt_float_or_na(w)} / {_fmt_float_or_na(b)} / {_safe_ratio_text(w, b)}",
                )
            )
            if w is None and sym in whatif_errors:
                s_rows.append(_kv(f"S {sym} reason", whatif_errors[sym]))
        u_fac = _limit_factor(fc, UFactor)
        s_fac = _limit_factor(fc, SFactor)
        u_section = {
            "title": f"[5-A] U（資本使用率） [ U={_breakdown_level_suffix(u_fac)} ]",
            "rows": u_rows,
        }
        s_section = {
            "title": f"[5-B] S（SPAN） [ S={_breakdown_level_suffix(s_fac)} ]",
            "rows": s_rows,
        }

    position_ctx = {
        "symbols": [],
        "futures_target_rows": [],
        "options_rows": [],
    }
    if positions_detail and target_base_by_symbol is not None and modes_by_symbol is not None:
        position_ctx = build_position_report_context(
            ["NQ", "GC"],
            positions_detail=positions_detail,
            target_base_by_symbol=target_base_by_symbol,
            modes_by_symbol=modes_by_symbol,
            altitude=str(altitude),
        )

    return {
        "date_iso": date_iso,
        "price_sections": price_sections,
        "volatility_sections": volatility_sections,
        "credit_sections": credit_sections,
        "r_section": r_section,
        "u_section": u_section,
        "s_section": s_section,
        "pos_symbols": position_ctx["symbols"],
        "pos_futures_target_rows": position_ctx["futures_target_rows"],
        "pos_options_rows": position_ctx["options_rows"],
        "hit_legend": BREAKDOWN_HIT_LEGEND,
    }


def format_breakdown_report(
    fc: "FlightController",
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]] = None,
    target_base_by_symbol: Optional[dict[str, float]] = None,
    modes_by_symbol: Optional[dict[str, ModeType]] = None,
    template_name: str = BREAKDOWN_TEMPLATE,
) -> str:
    """
    Layer 2 シグナル内訳レポート文字列をテンプレートで生成する。
    bundle は fc.get_last_bundle() から取得する（refresh 済みの FC を渡すこと）。

    :param fc: refresh 済みの FlightController。
    :param template_name: テンプレートファイル名。
    :return: レポート文字列。
    """
    bundle = fc.get_last_bundle()
    if bundle is None:
        raise ValueError("format_breakdown_report requires fc.refresh() to have been called first")
    altitude = fc.last_altitude_regime
    if altitude is None:
        raise ValueError("format_breakdown_report requires fc.refresh() so last_altitude_regime is set")
    context = _build_breakdown_report_context(
        fc,
        bundle,
        altitude=altitude,
        positions_detail=positions_detail,
        target_base_by_symbol=target_base_by_symbol,
        modes_by_symbol=modes_by_symbol,
    )
    return render(template_name, context)
