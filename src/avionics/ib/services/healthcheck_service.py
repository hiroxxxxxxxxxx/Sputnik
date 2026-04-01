from __future__ import annotations

from typing import Any, Dict

from ..infra.session import with_ib_connection
from .whatif_order_service import IBWhatIfOrderService


async def run_ib_healthcheck(
    host: str,
    port: int,
    *,
    client_id: int = 3,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ib_connected": False,
        "historical_nq_ok": False,
        "historical_nq_bars": None,
        "historical_nq_error": None,
        "whatif_mnq_ok": False,
        "whatif_mnq_margin_change": None,
        "whatif_mnq_margin_path": None,
        "whatif_mnq_error": None,
        "whatif_mnq_account": None,
        "whatif_mnq_warning": None,
        "whatif_mnq_state_source": None,
        "whatif_mnq_contract": "none",
        "whatif_stock_ok": False,
        "whatif_stock_margin_change": None,
        "whatif_stock_margin_path": None,
        "whatif_stock_error": None,
        "whatif_stock_warning": None,
        "whatif_stock_state_source": None,
        "overall": "FAIL",
    }
    try:
        async with with_ib_connection(
            host, port, client_id=client_id, timeout=timeout
        ) as ib:
            out["ib_connected"] = True
            whatif_order_service = IBWhatIfOrderService(ib)

            try:
                from ib_async import ContFuture  # type: ignore

                bars = await ib.reqHistoricalDataAsync(
                    ContFuture(symbol="NQ", exchange="CME", currency="USD"),
                    endDateTime="",
                    durationStr="3 D",
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=True,
                    timeout=12,
                )
                bars_len = len(bars) if bars is not None else 0
                out["historical_nq_bars"] = bars_len
                out["historical_nq_ok"] = bars_len >= 2
                if bars_len < 2:
                    out["historical_nq_error"] = f"insufficient bars: {bars_len}"
            except Exception as e:
                out["historical_nq_error"] = f"{type(e).__name__}: {e}"

            try:
                probe = await whatif_order_service.preview_whatif_for_symbol(symbol="MNQ")
                out["whatif_mnq_ok"] = True
                out["whatif_mnq_account"] = probe["account"]
                out["whatif_mnq_contract"] = probe["contract_diag"]
                out["whatif_mnq_margin_change"] = probe["margin_change"]
                out["whatif_mnq_margin_path"] = probe["margin_path"]
                out["whatif_mnq_warning"] = probe["warning"]
                out["whatif_mnq_state_source"] = probe["state_source"]
            except Exception as e:
                out["whatif_mnq_error"] = f"{type(e).__name__}: {e}"

            try:
                probe = await whatif_order_service.preview_whatif_for_symbol(
                    symbol="AAPL", account=out["whatif_mnq_account"]
                )
                out["whatif_stock_ok"] = True
                out["whatif_stock_margin_change"] = probe["margin_change"]
                out["whatif_stock_margin_path"] = probe["margin_path"]
                out["whatif_stock_warning"] = probe["warning"]
                out["whatif_stock_state_source"] = probe["state_source"]
            except Exception as e:
                out["whatif_stock_error"] = f"{type(e).__name__}: {e}"
    except Exception:
        out["overall"] = "FAIL"
        return out

    hist_ok = bool(out["historical_nq_ok"])
    whatif_ok = bool(out["whatif_mnq_ok"])
    if hist_ok and whatif_ok:
        out["overall"] = "OK"
    elif out["ib_connected"]:
        out["overall"] = "DEGRADED"
    else:
        out["overall"] = "FAIL"
    return out
