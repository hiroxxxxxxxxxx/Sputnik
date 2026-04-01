"""IB healthcheck レポートのテンプレートレンダリング。"""

from __future__ import annotations

from reports._render import render


HEALTH_TEMPLATE = "health_report.txt"


def _build_health_report_context(out: dict[str, object]) -> dict[str, object]:
    """run_ib_healthcheck の結果をテンプレート向け context に変換する。"""
    ib_ok = bool(out.get("ib_connected"))
    hist_ok = bool(out.get("historical_nq_ok"))
    hist_bars = out.get("historical_nq_bars")
    hist_err = out.get("historical_nq_error") or "none"
    mnq_ok = bool(out.get("whatif_mnq_ok"))
    mnq_margin_path = out.get("whatif_mnq_margin_path") or "none"
    mnq_account = out.get("whatif_mnq_account") or "none"
    mnq_warning = out.get("whatif_mnq_warning") or "none"
    mnq_err = out.get("whatif_mnq_error") or "none"
    mnq_contract = out.get("whatif_mnq_contract") or "none"
    stock_ok = bool(out.get("whatif_stock_ok"))
    stock_margin_path = out.get("whatif_stock_margin_path") or "none"
    stock_warning = out.get("whatif_stock_warning") or "none"
    stock_err = out.get("whatif_stock_error") or "none"
    overall = out.get("overall") or "FAIL"

    return {
        "ib_socket_status": "OK" if ib_ok else "FAIL",
        "historical_nq_status": "OK" if hist_ok else "FAIL",
        "historical_nq_bars": hist_bars,
        "historical_nq_error": hist_err,
        "whatif_mnq_status": "OK" if mnq_ok else "FAIL",
        "whatif_mnq_path": mnq_margin_path,
        "whatif_mnq_account": mnq_account,
        "whatif_mnq_warning": mnq_warning,
        "whatif_mnq_error": mnq_err,
        "whatif_mnq_contract": mnq_contract,
        "whatif_aapl_status": "OK" if stock_ok else "FAIL",
        "whatif_aapl_path": stock_margin_path,
        "whatif_aapl_warning": stock_warning,
        "whatif_aapl_error": stock_err,
        "overall": overall,
    }


def format_health_report(
    out: dict[str, object],
    template_name: str = HEALTH_TEMPLATE,
) -> str:
    """run_ib_healthcheck の結果をテンプレートで整形して返す。"""
    context = _build_health_report_context(out)
    return render(template_name, context)
