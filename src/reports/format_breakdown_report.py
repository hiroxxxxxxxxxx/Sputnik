"""
Layer 2 シグナル内訳（breakdown / detail）レポートのテンプレートレンダリング。

責務: フォーマット後の値のみ渡す。表示文言はテンプレートに記載。
bundle は FC から get_last_bundle() で取得する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reports._render import render

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import SignalBundle

BREAKDOWN_TEMPLATE = "breakdown_report.txt"


def build_breakdown_report_context(bundle: "SignalBundle") -> dict[str, Any]:
    """
    Layer 2 シグナル内訳用のテンプレートコンテキストを組み立てる。
    フォーマット後の値のみ渡し、表示文言はテンプレート側で組み立てる。
    """
    price_rows: list[dict[str, Any]] = []
    for sym, ps in bundle.price_signals.items():
        price_rows.append({
            "symbol": sym,
            "trend": ps.trend,
            "daily_change": f"{ps.daily_change:.4f}",
            "cum5": f"{ps.cum5_change:.4f}",
            "cum2": str(ps.cum2_change),
            "downside_gap": f"{ps.downside_gap:.4f}",
        })

    volatility_rows: list[dict[str, Any]] = []
    for sym, vs in bundle.volatility_signals.items():
        volatility_rows.append({
            "symbol": sym,
            "index_value": f"{vs.index_value:.2f}",
            "altitude": vs.altitude,
        })

    liquidity_credit: dict[str, Any] | None = None
    if bundle.liquidity_credit:
        lc = bundle.liquidity_credit
        liquidity_credit = {
            "below_sma20": lc.below_sma20,
            "daily_change": str(lc.daily_change),
            "altitude": lc.altitude,
        }
    liquidity_credit_lqd: dict[str, Any] | None = None
    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
    if lc_lqd:
        liquidity_credit_lqd = {
            "below_sma20": lc_lqd.below_sma20,
            "daily_change": str(lc_lqd.daily_change),
            "altitude": lc_lqd.altitude,
        }

    liquidity_tip: dict[str, Any] | None = None
    if bundle.liquidity_tip:
        lt = bundle.liquidity_tip
        liquidity_tip = {
            "tip_drawdown_from_high": str(lt.tip_drawdown_from_high),
            "altitude": lt.altitude,
        }

    capital_row: dict[str, Any] | None = None
    if bundle.capital_signals:
        cs = bundle.capital_signals
        capital_row = {
            "mm_over_nlv": f"{cs.mm_over_nlv:.4f}",
            "span_ratio": f"{cs.span_ratio:.4f}",
        }

    return {
        "price_rows": price_rows,
        "volatility_rows": volatility_rows,
        "liquidity_credit": liquidity_credit,
        "liquidity_credit_lqd": liquidity_credit_lqd,
        "liquidity_tip": liquidity_tip,
        "capital_row": capital_row,
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
    context = build_breakdown_report_context(bundle)
    return render(template_name, context)
