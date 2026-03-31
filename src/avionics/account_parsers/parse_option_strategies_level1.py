from __future__ import annotations

from typing import Any, Dict, List


def _sum_family_options(opt: dict[str, float], *, family: str) -> tuple[float, float, float, float]:
    if family == "NQ":
        call_buy = float(opt.get("nq_call_buy", 0.0)) + float(opt.get("mnq_call_buy", 0.0))
        call_sell = float(opt.get("nq_call_sell", 0.0)) + float(opt.get("mnq_call_sell", 0.0))
        put_buy = float(opt.get("nq_put_buy", 0.0)) + float(opt.get("mnq_put_buy", 0.0))
        put_sell = float(opt.get("nq_put_sell", 0.0)) + float(opt.get("mnq_put_sell", 0.0))
        return call_buy, call_sell, put_buy, put_sell
    call_buy = float(opt.get("gc_call_buy", 0.0)) + float(opt.get("mgc_call_buy", 0.0))
    call_sell = float(opt.get("gc_call_sell", 0.0)) + float(opt.get("mgc_call_sell", 0.0))
    put_buy = float(opt.get("gc_put_buy", 0.0)) + float(opt.get("mgc_put_buy", 0.0))
    put_sell = float(opt.get("gc_put_sell", 0.0)) + float(opt.get("mgc_put_sell", 0.0))
    return call_buy, call_sell, put_buy, put_sell


def parse_option_strategies_level1_from_option_detail(
    option_detail: dict[str, float], *, family: str
) -> dict[str, Any]:
    call_buy, call_sell, put_buy, put_sell = _sum_family_options(option_detail, family=family)
    put_short = max(put_sell, 0.0)
    put_long = max(put_buy, 0.0)
    pb = min(put_short, put_long / 2.0)
    rem_short = max(put_short - pb, 0.0)
    rem_long = max(put_long - 2.0 * pb, 0.0)
    bps = min(rem_short, rem_long)
    rem_short -= bps
    rem_long -= bps
    cc = max(call_sell - call_buy, 0.0)
    rem_call_buy = max(call_buy - call_sell, 0.0)
    unclassified = rem_short + rem_long + rem_call_buy
    return {
        "PB": pb,
        "BPS": bps,
        "CC": cc,
        "UNCLASSIFIED": unclassified,
        "UNCLASSIFIED_DETAIL": {
            "put_buy": rem_long,
            "put_sell": rem_short,
            "call_buy": rem_call_buy,
            "call_sell": 0.0,
        },
    }


def parse_option_strategies_level1_from_rows(
    symbols: List[str], options_rows: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    by_symbol = {str(r["symbol"]): r for r in options_rows}
    for sym in symbols:
        if sym not in ("NQ", "GC"):
            continue
        row = by_symbol.get(sym)
        if row is None:
            continue
        out[sym] = parse_option_strategies_level1_from_option_detail(row, family=sym)
    return out
