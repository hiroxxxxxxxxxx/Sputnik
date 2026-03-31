from __future__ import annotations

from typing import Any, Dict, List


def _normalize_position_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s in ("NQ", "MNQ"):
        return "NQ"
    if s in ("GC", "MGC"):
        return "GC"
    return s


def parse_position_detail_from_ib_positions(
    symbols: List[str], positions: List[Any]
) -> Dict[str, Dict[str, Dict[str, float]]]:
    symbol_set = {s.strip().upper() for s in symbols}
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    future_bs_keys = {
        "NQ": ("nq_buy", "nq_sell"),
        "MNQ": ("mnq_buy", "mnq_sell"),
        "GC": ("gc_buy", "gc_sell"),
        "MGC": ("mgc_buy", "mgc_sell"),
    }
    for sym in symbol_set:
        out[sym] = {
            "futures": {
                "nq_buy": 0.0,
                "nq_sell": 0.0,
                "mnq_buy": 0.0,
                "mnq_sell": 0.0,
                "gc_buy": 0.0,
                "gc_sell": 0.0,
                "mgc_buy": 0.0,
                "mgc_sell": 0.0,
            },
            "options": {
                "nq_call_buy": 0.0,
                "nq_call_sell": 0.0,
                "nq_put_buy": 0.0,
                "nq_put_sell": 0.0,
                "mnq_call_buy": 0.0,
                "mnq_call_sell": 0.0,
                "mnq_put_buy": 0.0,
                "mnq_put_sell": 0.0,
                "gc_call_buy": 0.0,
                "gc_call_sell": 0.0,
                "gc_put_buy": 0.0,
                "gc_put_sell": 0.0,
                "mgc_call_buy": 0.0,
                "mgc_call_sell": 0.0,
                "mgc_put_buy": 0.0,
                "mgc_put_sell": 0.0,
            },
        }
    for pos in positions:
        contract = getattr(pos, "contract", None)
        if contract is None:
            continue
        raw_symbol = str(getattr(contract, "symbol", "")).strip().upper()
        group_symbol = _normalize_position_symbol(raw_symbol)
        if group_symbol not in symbol_set:
            continue
        qty = float(getattr(pos, "position", 0.0))
        sec_type = str(getattr(contract, "secType", "")).upper()
        right = str(getattr(contract, "right", "")).upper()
        detail = out[group_symbol]
        if sec_type in ("FUT", "CONTFUT"):
            bs = future_bs_keys.get(raw_symbol)
            if bs is not None:
                buy_k, sell_k = bs
                if qty >= 0:
                    detail["futures"][buy_k] += qty
                else:
                    detail["futures"][sell_k] += abs(qty)
        elif sec_type in ("OPT", "FOP"):
            prefix = raw_symbol.lower()
            if prefix not in ("nq", "mnq", "gc", "mgc"):
                continue
            if right == "P":
                if qty >= 0:
                    detail["options"][f"{prefix}_put_buy"] += qty
                else:
                    detail["options"][f"{prefix}_put_sell"] += abs(qty)
            else:
                if qty >= 0:
                    detail["options"][f"{prefix}_call_buy"] += qty
                else:
                    detail["options"][f"{prefix}_call_sell"] += abs(qty)
    return out
