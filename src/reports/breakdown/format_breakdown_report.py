"""Layer 2 シグナル内訳（breakdown / detail）レポートのテンプレートレンダリング。"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from avionics.compute import (
    liquidity_credit_canonical_inputs,
    liquidity_tip_canonical_drawdown,
    price_signals_p_input_tuple,
)
from cockpit.mode import ModeType
from reports._render import render
from reports.breakdown.breakdown_helpers import (
    BREAKDOWN_HIT_LEGEND,
    BREAKDOWN_LEVEL_STR,
    P_BREAKDOWN_HIT_MARKER,
    breakdown_level_suffix,
    factor_from_symbol,
    first_factor_among_symbols,
    fmt_float_or_na,
    fmt_pct,
    fmt_price,
    fmt_progress,
    kv,
    limit_factor,
    liquidity_credit_section,
    mark_hits,
    safe_ratio_text,
    scl_level_for_breakdown,
    v_confirm_days,
    v_factor_level,
)
from reports.position_report_context import build_position_report_context

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import AltitudeRegime, SignalBundle

BREAKDOWN_TEMPLATE = "breakdown_report.txt"
_PT_IDS = ("1-A", "1-B")
_V_IDS = ("2-A", "2-B")
_C_IDS = ("3-A", "3-B")


def _collect_price_symbols(bundle: "SignalBundle") -> list[str]:
    symbols = [s for s in ("NQ", "GC") if s in bundle.price_signals]
    symbols += sorted(s for s in bundle.price_signals if s not in ("NQ", "GC"))
    return symbols


def _price_rows(ps: Any) -> list[dict[str, Any]]:
    dc, c5, hg, tr, c2 = price_signals_p_input_tuple(ps)
    return [
        kv("清算値", fmt_price(ps.last_close)),
        kv("20SMA", fmt_price(ps.sma20)),
        kv("20SMA乖離率", fmt_pct(ps.sma20_gap)),
        kv("トレンド", tr, row_key="trend"),
        kv("日次変化率", fmt_pct(dc), row_key="daily_change"),
        kv("2日累積変動率", fmt_pct(c2), row_key="cum2_change"),
        kv("5日累積変動率", fmt_pct(c5), row_key="cum5_change"),
        kv("20日高値", fmt_price(ps.high_20)),
        kv("20日高値乖離率", fmt_pct(hg), row_key="high_20_gap"),
    ]


def _apply_p_hits(rows: list[dict[str, Any]], p_factor: Any, ps: Any) -> None:
    from avionics.factors.p_factor import p_classify_row_with_reason, p_failed_p0_row_keys
    from reports.breakdown.breakdown_p_hits import p_breakdown_hit_row_keys

    if p_factor is not None:
        dc, c5, hg, tr, c2 = price_signals_p_input_tuple(ps)
        if hg is None:
            rows.append(kv("P 注釈", "high_20_gap 未取得のため P 分類マークを付けていません。"))
            return
        try:
            lvl_snap, rid_snap = p_classify_row_with_reason(p_factor.thresholds, dc, c5, hg, tr, c2)
            rid = rid_snap
            if rid == "P0_calm":
                mark_hits(rows, set())
            else:
                p0_set = set(p_failed_p0_row_keys(p_factor.thresholds, dc, c5, hg, tr))
                mark_hits(rows, set(p_breakdown_hit_row_keys(rid)) | p0_set)
            if int(p_factor.level) != int(lvl_snap):
                rows.append(kv("P 注釈", "表示時点の因子レベルと最新行分類が一致しません（refresh 順序を確認）。"))
        except ValueError:
            pass


def _build_price_sections(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> list[dict[str, Any]]:
    from avionics.factors.p_factor import PFactor
    from avionics.factors.t_factor import TFactor

    sections: list[dict[str, Any]] = []
    for idx, sym in enumerate(price_symbols):
        ps = bundle.price_signals[sym]
        sid = _PT_IDS[idx] if idx < len(_PT_IDS) else str(idx + 1)
        rows = _price_rows(ps)
        p_factor = factor_from_symbol(fc, sym, PFactor)
        t_fac = factor_from_symbol(fc, sym, TFactor)
        p_level = breakdown_level_suffix(p_factor)
        _apply_p_hits(rows, p_factor, ps)
        t_level = breakdown_level_suffix(t_fac)
        for r in rows:
            r.pop("row_key", None)
        sections.append(
            {
                "section_id": sid,
                "symbol": sym,
                "p_level": p_level,
                "t_level": t_level,
                "rows": rows,
            }
        )
    return sections


def _build_t_section(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> dict[str, Any] | None:
    if not price_symbols:
        return None
    t_rows = [
        kv(f"{sym} トレンド", price_signals_p_input_tuple(bundle.price_signals[sym])[3])
        for sym in price_symbols
    ]
    return {"section_id": "5", "scl_level": BREAKDOWN_LEVEL_STR.get(scl_level_for_breakdown(fc), "?"), "rows": t_rows}


def _collect_vol_symbols(bundle: "SignalBundle") -> list[str]:
    symbols = [s for s in ("NQ", "GC") if s in bundle.volatility_signals]
    symbols += sorted(s for s in bundle.volatility_signals if s not in ("NQ", "GC"))
    return symbols


def _volatility_rows(vs: Any) -> list[dict[str, Any]]:
    return [kv("ボラ指数 (VXN/GVZ 相当)", f"{vs.index_value:.2f}", row_key="index_value"), kv("20日高値", fmt_price(vs.high_20))]


def _build_volatility_sections(fc: "FlightController", bundle: "SignalBundle", vol_symbols: list[str], *, altitude: "AltitudeRegime") -> list[dict[str, Any]]:
    from avionics.factors.v_factor import VFactor
    from reports.breakdown.breakdown_v_hits import v_breakdown_hit_row_keys

    sections: list[dict[str, Any]] = []
    for idx, sym in enumerate(vol_symbols):
        vs = bundle.volatility_signals[sym]
        v_fac = factor_from_symbol(fc, sym, VFactor)
        v_th = v_fac._get_thresholds(altitude) if v_fac is not None else None
        v1_days, v2_days = v_confirm_days(fc, sym, altitude=altitude)
        v_level = v_factor_level(fc, sym)
        sid = _V_IDS[idx] if idx < len(_V_IDS) else str(idx + 10)
        rows = _volatility_rows(vs)
        v_hit_keys = v_breakdown_hit_row_keys(vs, v_th, v_level, v1_days)
        if v_level == 1:
            x1 = min(vs.recovery_confirm_satisfied_days_v1_off, v1_days)
            rows.append(kv("V1→V0復帰判定", fmt_progress(x1, v1_days), row_key="v1_recovery"))
            v_hit_keys.add("v1_recovery")
            if vs.recovery_confirm_satisfied_days_v1_off >= v1_days:
                rows.extend([kv(" ・ノックイン成立", "はい" if vs.v1_to_v0_knock_in_ok else "いいえ", row_key="v1_knock_in"), kv(" ・ノックイン判定時刻", vs.knock_in_bar_end or "—")])
                v_hit_keys.add("v1_knock_in")
        elif v_level == 2:
            x2 = min(vs.recovery_confirm_satisfied_days_v2_off, v2_days)
            rows.append(kv("V2→V1復帰判定", fmt_progress(x2, v2_days), row_key="v2_recovery"))
        mark_hits(rows, v_hit_keys)
        for r in rows:
            r.pop("row_key", None)
        sections.append({"section_id": sid, "symbol": sym, "v_level": BREAKDOWN_LEVEL_STR[v_level], "rows": rows})
    return sections


def _build_credit_sections(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> list[dict[str, Any]]:
    from avionics.factors.c_factor import CFactor, c_breakdown_hit_row_keys_from_snapshot

    c_fac = first_factor_among_symbols(fc, price_symbols, CFactor)
    c_lv = breakdown_level_suffix(c_fac)
    sections: list[dict[str, Any]] = []
    if bundle.liquidity_credit_hyg:
        c_hyg = liquidity_credit_section(_C_IDS[0], "", bundle.liquidity_credit_hyg)
        c_hit_keys: set[str] = set()
        if c_fac is not None and int(c_fac.level) == 2:
            dc_th = float(c_fac.thresholds["daily_change_C2"])
            bs_h, dc_h = liquidity_credit_canonical_inputs(bundle.liquidity_credit_hyg)
            c_hit_keys = set(
                c_breakdown_hit_row_keys_from_snapshot(
                    bs_h,
                    dc_h,
                    dc_th,
                )
            )
        mark_hits(c_hyg["rows"], c_hit_keys)
        for r in c_hyg["rows"]:
            r.pop("row_key", None)
        c_hyg["credit_symbol"] = "HYG"
        c_hyg["c_level"] = c_lv
        c_hyg.pop("title", None)
        sections.append(c_hyg)
    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
    if lc_lqd:
        c_lqd = liquidity_credit_section(_C_IDS[1] if len(_C_IDS) > 1 else "3-B", "", lc_lqd)
        c_hit_keys: set[str] = set()
        if c_fac is not None and int(c_fac.level) == 2:
            dc_th = float(c_fac.thresholds["daily_change_C2"])
            bs_l, dc_l = liquidity_credit_canonical_inputs(lc_lqd)
            c_hit_keys = set(
                c_breakdown_hit_row_keys_from_snapshot(
                    bs_l,
                    dc_l,
                    dc_th,
                )
            )
        mark_hits(c_lqd["rows"], c_hit_keys)
        for r in c_lqd["rows"]:
            r.pop("row_key", None)
        c_lqd["credit_symbol"] = "LQD"
        c_lqd["c_level"] = c_lv
        c_lqd.pop("title", None)
        sections.append(c_lqd)
    return sections


def _build_r_section(fc: "FlightController", bundle: "SignalBundle", price_symbols: list[str]) -> dict[str, Any] | None:
    from avionics.factors.r_factor import RFactor
    from reports.breakdown.breakdown_r_hits import r_breakdown_hit_row_keys

    r_fac = first_factor_among_symbols(fc, price_symbols, RFactor)
    if not bundle.liquidity_tip:
        return None
    lt = bundle.liquidity_tip
    dd = liquidity_tip_canonical_drawdown(lt)
    rows = [
        kv("終値", fmt_price(lt.last_close)),
        kv("20日高値", fmt_price(lt.tip_reference_high)),
        kv("20日高値乖離率", fmt_pct(dd), row_key="tip_drawdown"),
    ]
    r_lv = int(r_fac.level) if r_fac is not None else 0
    mark_hits(rows, set(r_breakdown_hit_row_keys(r_lv)))
    for r in rows:
        r.pop("row_key", None)
    return {"section_id": "4", "r_level": breakdown_level_suffix(r_fac), "rows": rows}


def _build_limit_sections(fc: "FlightController", bundle: "SignalBundle") -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    from avionics.factors.s_factor import SFactor
    from avionics.factors.u_factor import UFactor

    if not bundle.capital_signals:
        return None, None
    cs = bundle.capital_signals
    u_rows = [kv("MM/NLV", f"{cs.mm_over_nlv:.2f} ({cs.mm_over_nlv * 100:.2f}%)")]
    s_rows = [kv("SPAN 比 (span_ratio)", f"{cs.span_ratio:.2f}")]
    baseline_map = cs.s_baseline_mm_per_lot
    whatif_map = cs.s_whatif_mm_per_lot
    whatif_errors = cs.s_whatif_errors or {}
    syms = sorted(baseline_map.keys()) if baseline_map else sorted(whatif_map.keys()) if whatif_map else []
    has_full_whatif = bool(syms and whatif_map is not None and all(sym in whatif_map for sym in syms))
    whatif_total = sum(float(whatif_map[s]) for s in syms) if has_full_whatif else None  # type: ignore[index]
    baseline_total = sum(float(baseline_map[s]) for s in syms if baseline_map and s in baseline_map) if baseline_map is not None and syms else None
    s_rows.extend(
        [
            kv("S whatIf total", fmt_float_or_na(whatif_total)),
            kv("S baseline total", fmt_float_or_na(baseline_total)),
            kv("S total ratio (whatIf/base)", safe_ratio_text(whatif_total, baseline_total)),
        ]
    )
    for sym in ("NQ", "GC"):
        w = float(whatif_map[sym]) if whatif_map is not None and sym in whatif_map else None
        b = float(baseline_map[sym]) if baseline_map is not None and sym in baseline_map else None
        s_rows.append(kv(f"S {sym} (whatIf/base/ratio)", f"{fmt_float_or_na(w)} / {fmt_float_or_na(b)} / {safe_ratio_text(w, b)}"))
        if w is None and sym in whatif_errors:
            s_rows.append(kv(f"S {sym} reason", whatif_errors[sym]))
    u_section = {"section_id": "6-A", "u_level": breakdown_level_suffix(limit_factor(fc, UFactor)), "rows": u_rows}
    s_section = {"section_id": "6-B", "s_level": breakdown_level_suffix(limit_factor(fc, SFactor)), "rows": s_rows}
    return u_section, s_section


def _build_position_ctx(
    *,
    altitude: "AltitudeRegime",
    positions_detail: Optional[dict[str, dict[str, dict[str, float]]]],
    target_base_by_symbol: Optional[dict[str, float]],
    modes_by_symbol: Optional[dict[str, ModeType]],
) -> dict[str, Any]:
    if positions_detail and target_base_by_symbol is not None and modes_by_symbol is not None:
        return build_position_report_context(
            ["NQ", "GC"],
            positions_detail=positions_detail,
            target_base_by_symbol=target_base_by_symbol,
            modes_by_symbol=modes_by_symbol,
            altitude=str(altitude),
        )
    return {"symbols": [], "futures_target_rows": [], "options_rows": []}


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
    price_symbols = _collect_price_symbols(bundle)
    price_sections = _build_price_sections(fc, bundle, price_symbols)
    t_section = _build_t_section(fc, bundle, price_symbols)
    vol_symbols = _collect_vol_symbols(bundle)
    volatility_sections = _build_volatility_sections(fc, bundle, vol_symbols, altitude=altitude)
    credit_sections = _build_credit_sections(fc, bundle, price_symbols)
    r_section = _build_r_section(fc, bundle, price_symbols)
    u_section, s_section = _build_limit_sections(fc, bundle)
    position_ctx = _build_position_ctx(
        altitude=altitude,
        positions_detail=positions_detail,
        target_base_by_symbol=target_base_by_symbol,
        modes_by_symbol=modes_by_symbol,
    )
    context = {
        "date_iso": date_iso,
        "price_sections": price_sections,
        "t_section": t_section,
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
    return render(template_name, context)
