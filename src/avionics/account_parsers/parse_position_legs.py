from __future__ import annotations

from typing import Any, Dict, List

from avionics.data.futures_micro_equiv import signed_future_root_qty_to_micro_equivalent


def _normalize_position_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s in ("NQ", "MNQ"):
        return "NQ"
    if s in ("GC", "MGC"):
        return "GC"
    return s


def parse_position_legs_from_ib_positions(
    symbols: List[str], positions: List[Any]
) -> Dict[str, Dict[str, float]]:
    symbol_set = {s.strip().upper() for s in symbols}
    out: Dict[str, Dict[str, float]] = {
        s: {"future": 0.0, "k1": 0.0, "k2": 0.0} for s in symbol_set
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
        legs = out[group_symbol]
        if sec_type in ("FUT", "CONTFUT"):
            legs["future"] += signed_future_root_qty_to_micro_equivalent(raw_symbol, qty)
        elif sec_type in ("OPT", "FOP"):
            if right == "P":
                legs["k2"] += qty
            else:
                legs["k1"] += qty
    return out
