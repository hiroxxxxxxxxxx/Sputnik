from __future__ import annotations

from typing import Any


def contract_for_price(symbol: str) -> Any:
    """価格系列用の IB 契約。ContFuture + 根シンボル（NQ/GC）。"""
    from ib_async import ContFuture

    m = {"NQ": ("NQ", "CME", "USD"), "GC": ("GC", "COMEX", "USD")}
    if symbol in m:
        s, ex, cur = m[symbol]
        return ContFuture(symbol=s, exchange=ex, currency=cur)
    return ContFuture(symbol=symbol, exchange="SMART", currency="USD")


def contract_for_volatility(symbol: str) -> Any:
    """ボラティリティ指数用。VXN/GVZ は IND。"""
    from ib_async import Index

    ex = "CBOE" if symbol in ("VXN", "VIX", "GVZ") else "SMART"
    return Index(symbol=symbol, exchange=ex, currency="USD")


def contract_for_etf(symbol: str) -> Any:
    """ETF（HYG, LQD, TIP 等）用。"""
    from ib_async import Stock

    return Stock(symbol=symbol, exchange="SMART", currency="USD")


def contract_for_micro_future(symbol: str) -> Any:
    """S因子 whatIf 用のマイクロ先物契約。"""
    from ib_async import Future

    if symbol == "NQ":
        return Future(symbol="MNQ", exchange="CME", currency="USD")
    if symbol == "GC":
        return Future(symbol="MGC", exchange="COMEX", currency="USD")
    raise ValueError(f"Unsupported engine symbol for whatIf: {symbol}")
