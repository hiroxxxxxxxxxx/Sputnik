"""
レポート文字列を返す公開 API。IB 接続・bundle 取得・FC 更新・formatter 呼び出しを一括で行う。

IB 接続は avionics.ib.with_ib_fetcher に委譲（ib モジュール依存は avionics.ib に局所化）。
Script（telegram_cockpit_bot 等）は host, port, symbols を渡すだけ。
定義書「Phase 5」参照。LAYER_SCRIPT_REPORTS_FC 改善案に基づく。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from avionics.flight_controller import FlightController


@asynccontextmanager
async def _refreshed_fc(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> AsyncIterator["FlightController"]:
    """IB 接続 → build_cockpit_stack → fc.refresh の共通パイプライン。"""
    from avionics.ib import with_ib_fetcher
    from avionics.calendar import as_of_for_bundle
    from cockpit.stack import build_cockpit_stack

    async with with_ib_fetcher(host, port, client_id=client_id, timeout=timeout) as fetcher:
        fc, _ = build_cockpit_stack(symbols)
        as_of = as_of_for_bundle()
        await fc.refresh(fetcher, as_of, symbols)
        yield fc


async def fetch_cockpit_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    """IB から Raw を取得し FC.refresh で最新状態に更新したうえで、計器レポート文字列を返す。"""
    from reports.format_cockpit_report import format_cockpit_report

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as fc:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return await format_cockpit_report(fc, symbols, now_utc)


async def fetch_breakdown_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    """IB から Raw を取得し FC.refresh で bundle を組み立てたうえで、Layer 2 シグナル内訳を返す。"""
    from reports.format_breakdown_report import format_breakdown_report

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as fc:
        return format_breakdown_report(fc)


async def fetch_daily_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    """IB から Raw を取得し FC.refresh で最新状態に更新したうえで、Daily Flight Log を返す。"""
    from reports.format_daily_report import format_daily_report

    async with _refreshed_fc(host, port, symbols, client_id=client_id, timeout=timeout) as fc:
        return await format_daily_report(fc, symbols)
