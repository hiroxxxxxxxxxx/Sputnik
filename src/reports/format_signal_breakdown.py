"""
Layer 2 シグナルの整形表示。定義は avionics.data.signals / avionics.process.layer2.compute にあり、ここでは format のみ。
定義書「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from avionics.data.signals import SignalBundle


def format_signal_bundle_breakdown(bundle: SignalBundle) -> str:
    """
    Layer 2 シグナル（各因子の入力）を人が読める文字列で返す。
    因子の計算内訳確認用。
    """
    lines: list[str] = ["【Layer 2 シグナル内訳】"]
    for sym, ps in bundle.price_signals.items():
        lines.append(
            f"  P/T入力({sym}): trend={ps.trend} "
            f"daily_change={ps.daily_change:.4f} cum5={ps.cum5_change:.4f} "
            f"cum2={ps.cum2_change!s} downside_gap={ps.downside_gap:.4f}"
        )
    for sym, vs in bundle.volatility_signals.items():
        extra = f" 1h_knock_in_ok={vs.v1_to_v0_knock_in_ok}" if vs.v1_to_v0_knock_in_ok is not None else ""
        lines.append(f"  V入力({sym}): index_value={vs.index_value:.2f} altitude={vs.altitude}{extra}")
    if bundle.liquidity_credit:
        lc = bundle.liquidity_credit
        lines.append(
            f"  C(HYG): below_sma20={lc.below_sma20} daily_change={lc.daily_change!s} altitude={lc.altitude}"
        )
    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
    if lc_lqd:
        lines.append(
            f"  C(LQD): below_sma20={lc_lqd.below_sma20} daily_change={lc_lqd.daily_change!s} altitude={lc_lqd.altitude}"
        )
    if bundle.liquidity_tip:
        lt = bundle.liquidity_tip
        lines.append(
            f"  R(tip): tip_drawdown_from_high={lt.tip_drawdown_from_high!s} altitude={lt.altitude}"
        )
    if bundle.capital_signals:
        cs = bundle.capital_signals
        lines.append(f"  U/S入力: mm_over_nlv={cs.mm_over_nlv:.4f} span_ratio={cs.span_ratio:.4f}")
    return "\n".join(lines)
