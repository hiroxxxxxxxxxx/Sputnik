"""
Layer 2 シグナルの整形表示。定義は avionics.data.signals / avionics.compute にあり、ここでは format のみ。
`format_breakdown_report`（テンプレート）と同じレイアウト意図で CLI 向けに直列化する。
定義書「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from avionics.data.signals import SignalBundle

if TYPE_CHECKING:
    from avionics.data.factor_mapping import EngineFactorMapping

_MAX_CREDIT_HISTORY_ROWS = 15
_PT_IDS = ("1-A", "1-B")
_V_IDS = ("2-A", "2-B")
_C_IDS = ("3-A", "3-B")


def _fmt_price(value: float | None) -> str:
    return "—" if value is None else f"{float(value):,.2f}"


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{float(value) * 100:.2f}%"


def _v_confirm_days(mapping: Optional["EngineFactorMapping"], symbol: str) -> tuple[int, int]:
    """V因子の confirm_days（V1/V2）を取得する。取得できない場合は例外。"""
    if mapping is None:
        raise ValueError("format_signal_breakdown requires mapping to render V x/N progress")
    from avionics.factors.v_factor import VFactor

    for f in mapping.symbol_factors.get(symbol, []):
        if isinstance(f, VFactor):
            th = f._get_thresholds(f._altitude)
            return (int(th["V1_confirm_days"]), int(th["V2_confirm_days"]))
    raise ValueError(f"VFactor not found for symbol={symbol!r} in EngineFactorMapping")


def _fmt_progress(x: int, total: int) -> str:
    if total <= 0:
        raise ValueError(f"confirm_days must be positive, got {total}")
    return f"{x}/{total}日目"


def format_signal_breakdown(
    bundle: SignalBundle,
    mapping: Optional["EngineFactorMapping"] = None,
    *,
    date_iso: Optional[str] = None,
) -> str:
    """
    Layer 2 シグナル（各因子の入力）を人が読める文字列で返す。

    :param mapping: 指定時は銘柄ごとの復帰 x/N を P/T ブロック末尾に付記する。
    :param date_iso: 見出し日付（省略時は当日 UTC カレンダー日）。
    """
    header_d = date_iso or date.today().isoformat()
    lines: list[str] = [
        f"📐 【LAYER 2 BREAKDOWN】 {header_d}",
        "━━━━━━━━━━━━━━━━━━━━",
        "Layer 2 シグナル（各因子の入力値）内訳",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    price_symbols = [s for s in ("NQ", "GC") if s in bundle.price_signals]
    price_symbols += sorted(s for s in bundle.price_signals if s not in ("NQ", "GC"))
    for idx, sym in enumerate(price_symbols):
        ps = bundle.price_signals[sym]
        sid = _PT_IDS[idx] if idx < len(_PT_IDS) else str(idx + 1)
        settlement_txt = _fmt_price(ps.last_close)
        sma20_txt = _fmt_price(ps.sma20)
        sma20_gap_txt = _fmt_pct(ps.sma20_gap)
        high20_txt = _fmt_price(ps.high_20)
        high20_gap_txt = _fmt_pct(ps.high_20_gap)
        lines.append("────────────────────")
        lines.append(f"[{sid}] P/T 入力 <{sym}>")
        lines.append(f"settlement（清算値） | {settlement_txt}")
        lines.append(f"20SMA | {sma20_txt}")
        lines.append(f"20SMA乖離率 | {sma20_gap_txt}")
        lines.append(f"トレンド | {ps.trend}")
        lines.append(f"日次変化率 | {_fmt_pct(ps.daily_change)}")
        lines.append(f"2日累積変動率 | {_fmt_pct(ps.cum2_change)}")
        lines.append(f"5日累積変動率 | {_fmt_pct(ps.cum5_change)}")
        lines.append(f"20日高値 | {high20_txt}")
        lines.append(f"20日高値乖離率 | {high20_gap_txt}")
        lines.append("")

    vol_symbols = [s for s in ("NQ", "GC") if s in bundle.volatility_signals]
    vol_symbols += sorted(s for s in bundle.volatility_signals if s not in ("NQ", "GC"))
    for idx, sym in enumerate(vol_symbols):
        vs = bundle.volatility_signals[sym]
        knock = vs.v1_to_v0_knock_in_ok
        knock_txt = "—" if knock is None else ("はい" if knock else "いいえ")
        knockin_txt = "はい" if vs.is_intraday_condition_met else "いいえ"
        v1_days, v2_days = _v_confirm_days(mapping, sym)
        sid = _V_IDS[idx] if idx < len(_V_IDS) else str(idx + 10)
        lines.append("────────────────────")
        lines.append(f"[{sid}] V 入力 <{sym}>")
        lines.append(f"ボラ指数 (VXN/GVZ 相当) | {vs.index_value:.2f}")
        lines.append(f"20日高値 | {_fmt_price(vs.high_20)}")
        lines.append(f"V1→V0 ノックイン判定 | {knock_txt}")
        lines.append(f"ノックイン足 (bar_end) | {vs.knock_in_bar_end or '—'}")
        lines.append(f"ノックイン成立 | {knockin_txt}")
        lines.append(
            f"V1→V0復帰判定 | {_fmt_progress(vs.recovery_confirm_satisfied_days_v1_off, v1_days)}"
        )
        lines.append(
            f"V2→V1復帰判定 | {_fmt_progress(vs.recovery_confirm_satisfied_days_v2_off, v2_days)}"
        )
        lines.append("")

    if bundle.liquidity_credit_hyg:
        lc = bundle.liquidity_credit_hyg
        below_txt = "—" if lc.below_sma20 is None else ("Below SMA20" if lc.below_sma20 else "Above SMA20")
        dc_txt = _fmt_pct(lc.daily_change)
        lines.append("────────────────────")
        lines.append(f"[{_C_IDS[0]}] C（HYG / credit）")
        close_txt = _fmt_price(lc.last_close)
        sma_txt = _fmt_price(lc.sma20)
        sma_gap_txt = _fmt_pct(lc.sma20_gap)
        lines.append(f"終値 | {close_txt}")
        lines.append(f"SMA20 | {sma_txt}")
        lines.append(f"SMA20乖離率 | {sma_gap_txt}")
        lines.append(f"SMA20 位置 | {below_txt}")
        lines.append(f"日次変化率 | {dc_txt}")
        lines.append("（日次履歴・newest first）")
        lines.append("日付 | SMA20 | 日次変化率")
        for row in lc.daily_history_credit[:_MAX_CREDIT_HISTORY_ROWS]:
            d, below, dc_h = row[0], row[1], row[2]
            btxt = "Below" if below else "Above"
            lines.append(f"{d.isoformat()} | {btxt} | {_fmt_pct(dc_h)}")
        lines.append("")

    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
    if lc_lqd:
        lc = lc_lqd
        below_txt = "—" if lc.below_sma20 is None else ("Below SMA20" if lc.below_sma20 else "Above SMA20")
        dc_txt = _fmt_pct(lc.daily_change)
        cid = _C_IDS[1] if len(_C_IDS) > 1 else "3-B"
        lines.append("────────────────────")
        lines.append(f"[{cid}] C（LQD / credit）")
        close_txt = _fmt_price(lc.last_close)
        sma_txt = _fmt_price(lc.sma20)
        sma_gap_txt = _fmt_pct(lc.sma20_gap)
        lines.append(f"終値 | {close_txt}")
        lines.append(f"SMA20 | {sma_txt}")
        lines.append(f"SMA20乖離率 | {sma_gap_txt}")
        lines.append(f"SMA20 位置 | {below_txt}")
        lines.append(f"日次変化率 | {dc_txt}")
        lines.append("（日次履歴・newest first）")
        lines.append("日付 | SMA20 | 日次変化率")
        for row in lc.daily_history_credit[:_MAX_CREDIT_HISTORY_ROWS]:
            d, below, dc_h = row[0], row[1], row[2]
            btxt = "Below" if below else "Above"
            lines.append(f"{d.isoformat()} | {btxt} | {_fmt_pct(dc_h)}")
        lines.append("")

    if bundle.liquidity_tip:
        lt = bundle.liquidity_tip
        dd_txt = _fmt_pct(lt.tip_drawdown_from_high)
        close_txt = _fmt_price(lt.last_close)
        ref_high_txt = _fmt_price(lt.tip_reference_high)
        lines.append("────────────────────")
        lines.append("[4] R（TIP）")
        lines.append(f"終値 | {close_txt}")
        lines.append(f"20日高値 | {ref_high_txt}")
        lines.append(f"20日高値乖離率 | {dd_txt}")
        lines.append("")

    if bundle.capital_signals:
        cs = bundle.capital_signals
        lines.append("────────────────────")
        lines.append("[5] U/S（資本）")
        lines.append(f"MM/NLV | {cs.mm_over_nlv:.2f} ({cs.mm_over_nlv * 100:.2f}%)")
        lines.append(f"SPAN 比 (span_ratio) | {cs.span_ratio:.2f}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
