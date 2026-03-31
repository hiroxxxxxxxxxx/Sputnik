"""
IB（ib_async）依存を集約するパッケージ。

- IBRawFetcher: Layer 1 のみ（Raw 取得）。with_ib_fetcher が yield する型。FC.refresh に渡す。
戻りは RawMarketSnapshot（NQ/GC固定DTO）+ Optional[RawCapitalSnapshot]。
SignalBundle は FC.refresh(data_source, as_of, symbols) のあと fc.get_last_bundle() で取得する。
reports / scripts は avionics.ib のみ import し、ib_async は直接 import しない。
"""

from .fetcher import IBRawFetcher
from .schedule_scan import fetch_trading_hours_async, run_daily_schedule_scan
from .session import (
    check_ib_connection,
    run_ib_healthcheck,
    with_ib_connection,
    with_ib_fetcher,
)

__all__ = [
    "check_ib_connection",
    "fetch_trading_hours_async",
    "IBRawFetcher",
    "run_ib_healthcheck",
    "run_daily_schedule_scan",
    "with_ib_connection",
    "with_ib_fetcher",
]
