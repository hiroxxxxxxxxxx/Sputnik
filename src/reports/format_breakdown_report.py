"""
Layer 2 シグナル内訳（breakdown / detail）レポートのテンプレートレンダリング。

責務: フォーマット後の値のみ渡す。表示文言・レイアウトはテンプレートに記載。
`daily_flight_log.txt` と同様の区切り線・セクション見出しで読みやすくする。
bundle は FC から get_last_bundle() で取得する。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from reports._render import render

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import AltitudeRegime, LiquiditySignals, SignalBundle

BREAKDOWN_TEMPLATE = "breakdown_report.txt"

_PT_IDS = ("1-A", "1-B")
_V_IDS = ("2-A", "2-B")
_C_IDS = ("3-A", "3-B")


def _kv(label: str, value: str) -> dict[str, str]:
    return {"label": label, "value": value}


def _fmt_price(value: float | None) -> str:
    return "—" if value is None else f"{float(value):,.2f}"


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{float(value) * 100:.2f}%"


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
) -> dict[str, Any]:
    """
    Layer 2 シグナル内訳用のテンプレートコンテキストを組み立てる。
    """
    cap = fc.get_last_capital_snapshot()
    date_iso = cap.as_of.isoformat() if cap and getattr(cap, "as_of", None) else date.today().isoformat()

    price_symbols = [s for s in ("NQ", "GC") if s in bundle.price_signals]
    price_symbols += sorted(s for s in bundle.price_signals if s not in ("NQ", "GC"))

    price_sections: list[dict[str, Any]] = []
    for idx, sym in enumerate(price_symbols):
        ps = bundle.price_signals[sym]
        sid = _PT_IDS[idx] if idx < len(_PT_IDS) else str(idx + 1)
        settlement_txt = _fmt_price(ps.last_close)
        sma20_txt = _fmt_price(ps.sma20)
        sma20_gap_txt = _fmt_pct(ps.sma20_gap)
        high20_txt = _fmt_price(ps.high_20)
        high20_gap_txt = _fmt_pct(ps.high_20_gap)
        rows = [
            _kv("清算値", settlement_txt),
            _kv("20SMA", sma20_txt),
            _kv("20SMA乖離率", sma20_gap_txt),
            _kv("トレンド", ps.trend),
            _kv("日次変化率", _fmt_pct(ps.daily_change)),
            _kv("2日累積変動率", _fmt_pct(ps.cum2_change)),
            _kv("5日累積変動率", _fmt_pct(ps.cum5_change)),
            _kv("20日高値", high20_txt),
            _kv("20日高値乖離率", high20_gap_txt),
        ]
        price_sections.append({
            "section_id": sid,
            "title": f"P/T 入力 <{sym}>",
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
            "title": f"V 入力 <{sym}>",
            "rows": rows,
        })

    credit_sections: list[dict[str, Any]] = []
    if bundle.liquidity_credit_hyg:
        credit_sections.append(
            _liquidity_credit_section(
                _C_IDS[0],
                "C（HYG）",
                bundle.liquidity_credit_hyg,
            )
        )
    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
    if lc_lqd:
        credit_sections.append(
            _liquidity_credit_section(
                _C_IDS[1] if len(_C_IDS) > 1 else "3-B",
                "C（LQD）",
                lc_lqd,
            )
        )

    r_section: dict[str, Any] | None = None
    if bundle.liquidity_tip:
        lt = bundle.liquidity_tip
        dd_txt = _fmt_pct(lt.tip_drawdown_from_high)
        close_txt = _fmt_price(lt.last_close)
        ref_high_txt = _fmt_price(lt.tip_reference_high)
        r_section = {
            "rows": [
                _kv("終値", close_txt),
                _kv("20日高値", ref_high_txt),
                _kv("20日高値乖離率", dd_txt),
            ],
        }

    capital_section: dict[str, Any] | None = None
    if bundle.capital_signals:
        cs = bundle.capital_signals
        capital_section = {
            "rows": [
                _kv("MM/NLV", f"{cs.mm_over_nlv:.2f} ({cs.mm_over_nlv * 100:.2f}%)"),
                _kv("SPAN 比 (span_ratio)", f"{cs.span_ratio:.2f}"),
            ],
        }

    return {
        "date_iso": date_iso,
        "price_sections": price_sections,
        "volatility_sections": volatility_sections,
        "credit_sections": credit_sections,
        "r_section": r_section,
        "capital_section": capital_section,
    }


def format_breakdown_report(
    fc: "FlightController",
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
    context = _build_breakdown_report_context(fc, bundle, altitude=altitude)
    return render(template_name, context)
