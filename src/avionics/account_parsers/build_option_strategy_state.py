from __future__ import annotations

from typing import Dict, List

from avionics.data.account_state import OptionStrategyState, UnclassifiedDetail

from .parse_option_strategies_level1 import parse_option_strategies_level1_from_option_detail


def build_option_strategy_state_from_option_detail(
    option_detail: dict[str, float], *, family: str
) -> Dict[str, OptionStrategyState]:
    parsed = parse_option_strategies_level1_from_option_detail(option_detail, family=family)
    out: Dict[str, OptionStrategyState] = {}
    for strategy in ("PB", "BPS", "CC", "UNCLASSIFIED"):
        qty = float(parsed[strategy])
        if strategy == "UNCLASSIFIED":
            d = parsed["UNCLASSIFIED_DETAIL"]
            out[strategy] = OptionStrategyState(
                strategy=strategy,
                qty=qty,
                attached=qty != 0.0,
                unclassified_detail=UnclassifiedDetail(
                    put_buy=float(d["put_buy"]),
                    put_sell=float(d["put_sell"]),
                    call_buy=float(d["call_buy"]),
                    call_sell=float(d["call_sell"]),
                ),
            )
        else:
            out[strategy] = OptionStrategyState(
                strategy=strategy,
                qty=qty,
                attached=qty != 0.0,
            )
    return out


def build_option_strategy_state_from_rows(
    symbols: List[str], options_rows: List[Dict[str, object]]
) -> Dict[str, Dict[str, OptionStrategyState]]:
    by_symbol = {str(r["symbol"]): r for r in options_rows}
    out: Dict[str, Dict[str, OptionStrategyState]] = {}
    for sym in symbols:
        if sym not in ("NQ", "GC"):
            continue
        row = by_symbol.get(sym)
        if row is None:
            continue
        out[sym] = build_option_strategy_state_from_option_detail(row, family=sym)
    return out


def resolve_attached_strategy_name(
    states_by_strategy: Dict[str, OptionStrategyState],
) -> str:
    attached = [
        name
        for name in ("PB", "BPS", "CC")
        if bool(states_by_strategy[name].attached)
    ]
    if len(attached) > 1:
        raise ValueError(f"multiple option strategies attached: {attached}")
    return attached[0] if attached else "NONE"
