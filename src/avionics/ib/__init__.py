"""
IB（ib_async）依存を集約するパッケージ。

- IBMarketDataService: Layer 1 のみ（Raw 取得）。with_ib_market_data_service が yield する型。FC.refresh に渡す。
戻りは RawMarketSnapshot（NQ/GC固定DTO）+ Optional[RawCapitalSnapshot]。
SignalBundle は FC.refresh(data_source, as_of, symbols) のあと fc.get_last_bundle() で取得する。
reports / scripts は avionics.ib のみ import し、ib_async は直接 import しない。
"""

from .infra import (
    check_ib_connection,
    with_ib_market_data_service,
    with_ib_connection,
)
from .services.healthcheck_service import run_ib_healthcheck
from .services.market_data_service import IBMarketDataService

__all__ = [
    "check_ib_connection",
    "IBMarketDataService",
    "run_ib_healthcheck",
    "with_ib_connection",
    "with_ib_market_data_service",
]
