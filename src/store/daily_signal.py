"""
日次 ``signal_daily`` の永続化（P2-4b）。

NY クローズ後のジョブから呼び出す。``as_of`` は呼び出し側で解決して渡すこと。
"""
from __future__ import annotations

import sqlite3
from datetime import date

from avionics.data.data_source import DataSource
from avionics.flight_controller import FlightController

from .signal_daily import upsert_signal_daily


async def persist_signal_daily_after_refresh(
    conn: sqlite3.Connection,
    fc: FlightController,
    data_source: DataSource,
    symbols: list[str],
    *,
    as_of: date,
) -> date:
    """
    FC を refresh し、計器シグナルを ``signal_daily`` に upsert する。

    :param as_of: 保存対象日（欠損を補完しない）。
    :return: 保存に使った ``as_of``。
    """
    await fc.refresh(data_source, as_of, symbols)
    signal = await fc.get_flight_controller_signal()
    upsert_signal_daily(conn, as_of=as_of, signal=signal)
    return as_of
