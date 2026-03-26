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
    from avionics.data.signals import LiquiditySignals, SignalBundle

BREAKDOWN_TEMPLATE = "breakdown_report.txt"

_MAX_CREDIT_HISTORY_ROWS = 15

_PT_IDS = ("1-A", "1-B")
_V_IDS = ("2-A", "2-B")
_C_IDS = ("3-A", "3-B")


def _kv(label: str, value: str) -> dict[str, str]:
    return {"label": label, "value": value}


def _liquidity_credit_section(
    section_id: str,
    title: str,
    lc: "LiquiditySignals",
) -> dict[str, Any]:
    """C（credit）1本ぶん: スナップショット行 + 日次履歴テーブル用行。"""
    below_txt = "—" if lc.below_sma20 is None else ("Below SMA20" if lc.below_sma20 else "Above SMA20")
    dc = lc.daily_change
    dc_txt = "—" if dc is None else f"{float(dc):.4f}"
    close_txt = "—" if lc.last_close is None else f"{float(lc.last_close):,.4f}"
    sma_txt = "—" if lc.sma20 is None else f"{float(lc.sma20):,.4f}"
    rows = [
        _kv("終値", close_txt),
        _kv("SMA20", sma_txt),
        _kv("SMA20 位置", below_txt),
        _kv("日次変化率", dc_txt),
        _kv("高度 (altitude)", str(lc.altitude)),
    ]
    history_rows: list[dict[str, str]] = []
    for row in lc.daily_history_credit[:_MAX_CREDIT_HISTORY_ROWS]:
        d, below, dc_h = row[0], row[1], row[2]
        btxt = "Below" if below else "Above"
        history_rows.append({
            "date": d.isoformat(),
            "below": btxt,
            "daily_change": f"{dc_h:.4f}",
        })
    return {
        "section_id": section_id,
        "title": title,
        "rows": rows,
        "history_rows": history_rows,
    }


def _build_breakdown_report_context(fc: "FlightController", bundle: "SignalBundle") -> dict[str, Any]:
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
        rows = [
            _kv("終値", f"{ps.last_close:,.4f}"),
            _kv("トレンド", ps.trend),
            _kv("日次変化率", f"{ps.daily_change:.4f}"),
            _kv("cum5", f"{ps.cum5_change:.4f}"),
            _kv("cum2", str(ps.cum2_change)),
            _kv("downside_gap", f"{ps.downside_gap:.4f}"),
        ]
        prog = fc.mapping.get_recovery_progress(sym, bundle)
        if prog:
            rows.append(_kv("復帰進捗 (x/N)", " ".join(f"{k}={v}" for k, v in sorted(prog.items()))))
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
        knock_ok = vs.v1_to_v0_knock_in_ok
        knock_txt = "—" if knock_ok is None else ("はい" if knock_ok else "いいえ")
        intraday_txt = "はい" if vs.is_intraday_condition_met else "いいえ"
        sid = _V_IDS[idx] if idx < len(_V_IDS) else str(idx + 10)
        rows = [
            _kv("ボラ指数 (VXN/GVZ 相当)", f"{vs.index_value:.2f}"),
            _kv("高度 (altitude)", str(vs.altitude)),
            _kv("V1→V0 ノックイン判定", knock_txt),
            _kv("ノックイン足 (bar_end)", vs.knock_in_bar_end or "—"),
            _kv("イントラ条件成立", intraday_txt),
            _kv("V1_off 連続日数", str(vs.recovery_confirm_satisfied_days_v1_off)),
            _kv("V2_off 連続日数", str(vs.recovery_confirm_satisfied_days_v2_off)),
        ]
        volatility_sections.append({
            "section_id": sid,
            "title": f"V 入力 <{sym}>",
            "rows": rows,
        })

    credit_sections: list[dict[str, Any]] = []
    if bundle.liquidity_credit:
        credit_sections.append(
            _liquidity_credit_section(
                _C_IDS[0],
                "C（HYG）",
                bundle.liquidity_credit,
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
        dd = lt.tip_drawdown_from_high
        dd_txt = "—" if dd is None else f"{float(dd) * 100:.2f}%"
        close_txt = "—" if lt.last_close is None else f"{float(lt.last_close):,.4f}"
        ref_high_txt = "—" if lt.tip_reference_high is None else f"{float(lt.tip_reference_high):,.4f}"
        r_section = {
            "rows": [
                _kv("終値 (TIP)", close_txt),
                _kv("比較用高値 (窓内 max high)", ref_high_txt),
                _kv("高値比ドローダウン", dd_txt),
                _kv("高度 (altitude)", str(lt.altitude)),
            ],
        }

    capital_section: dict[str, Any] | None = None
    if bundle.capital_signals:
        cs = bundle.capital_signals
        capital_section = {
            "rows": [
                _kv("MM/NLV", f"{cs.mm_over_nlv:.4f} ({cs.mm_over_nlv * 100:.2f}%)"),
                _kv("SPAN 比 (span_ratio)", f"{cs.span_ratio:.4f}"),
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
    context = _build_breakdown_report_context(fc, bundle)
    return render(template_name, context)
