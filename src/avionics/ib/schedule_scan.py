"""
取引時間スキャン（IB 接続を使い、翌日以降の DST・短縮・休場を通知する）。

ib_async に依存する部分のみ。パース・判定ロジックは avionics.trading_hours にあり、ここでは
reqContractDetails で tradingHours を取得し、trading_hours の関数を呼ぶ。
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from ..trading_hours import (
    DaySchedule,
    check_upcoming_schedule,
    parse_trading_hours,
)


async def fetch_trading_hours_async(ib: Any, contract: Any) -> List[DaySchedule]:
    """
    IB の reqContractDetails で契約詳細を取得し、tradingHours をパースして返す。

    返る時間はその銘柄の主市場の現地時間（NQ/GC は ET）。日付は Trade Date。

    :param ib: 接続済み ib_async.IB インスタンス
    :param contract: ContFuture 等の契約
    :return: 日付順の DaySchedule リスト（avionics.trading_hours）。取得失敗時は []
    """
    try:
        details_list = await ib.reqContractDetailsAsync(contract)
    except Exception:
        return []
    if not details_list:
        return []
    details = details_list[0]
    raw = getattr(details, "tradingHours", None) or getattr(details, "trading_hours", None)
    if not raw:
        return []
    return parse_trading_hours(str(raw))


def _contract_for_symbol(symbol: str) -> Any:
    """価格系列用 IB 契約（tradingHours 取得用）。ib.fetcher と同じマッピング。"""
    from ib_async import ContFuture

    m = {"NQ": ("NQ", "CME", "USD"), "GC": ("GC", "COMEX", "USD")}
    if symbol in m:
        s, ex, cur = m[symbol]
        return ContFuture(symbol=s, exchange=ex, currency=cur)
    return ContFuture(symbol=symbol, exchange="SMART", currency="USD")


async def run_daily_schedule_scan(
    ib: Any,
    symbols: List[str],
    contract_resolver: Optional[Any] = None,
) -> List[Tuple[str, List[str]]]:
    """
    銘柄ごとに取引時間を取得し、翌日以降の変化についての通知メッセージを返す。

    :param ib: 接続済み ib_async.IB
    :param symbols: 銘柄リスト ["NQ", "GC"]
    :param contract_resolver: 銘柄 -> contract を返す callable。None のときは _contract_for_symbol を使用。
    :return: [(symbol, [message, ...]), ...]
    """
    resolve = contract_resolver if contract_resolver is not None else _contract_for_symbol
    results: List[Tuple[str, List[str]]] = []
    for symbol in symbols:
        try:
            contract = resolve(symbol)
            schedule_list = await fetch_trading_hours_async(ib, contract)
            messages = check_upcoming_schedule(schedule_list, days=3)
            results.append((symbol, messages))
        except Exception:
            results.append((symbol, ["取引時間の取得に失敗しました。"]))
    return results
