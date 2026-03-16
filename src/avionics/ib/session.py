"""
IB（ib_async）接続を局所化する窓口。

avionics.ib パッケージ以外では ib_async を import しない。
reports や scripts は with_ib_fetcher / with_ib_connection / check_ib_connection のみ使う。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from ib_async import IB

from .fetcher import IBRawFetcher


@asynccontextmanager
async def with_ib_fetcher(
    host: str,
    port: int,
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> AsyncIterator[Any]:
    """
    IB に接続し、Raw 取得用の IBRawFetcher を yield する。
    抜けたら disconnect。reports / scripts は fetcher を FC.refresh に渡して最新取得する。
    """
    ib = IB()
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=timeout)
    try:
        yield IBRawFetcher(ib)
    finally:
        ib.disconnect()


@asynccontextmanager
async def with_ib_connection(
    host: str,
    port: int,
    *,
    client_id: int = 3,
    timeout: float = 30.0,
) -> AsyncIterator[Any]:
    """
    IB に接続し、接続済み ib インスタンスを yield する。
    取引時間スキャン（run_daily_schedule_scan）等で使う。抜けたら disconnect。
    """
    ib = IB()
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=timeout)
    try:
        yield ib
    finally:
        ib.disconnect()


async def check_ib_connection(
    host: str,
    port: int,
    *,
    client_id: int = 3,
    timeout: float = 30.0,
) -> bool:
    """
    接続試行のみ行い、成功すれば True・失敗すれば False を返す。
    Gateway 起動完了通知用。呼び出し側は ib_async を import しない。
    """
    try:
        ib = IB()
        await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=timeout)
        ib.disconnect()
        return True
    except Exception:
        return False
