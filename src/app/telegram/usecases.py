from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from .env import env_host_port_symbols
from .messages import COCKPIT_BOT_COMMANDS_MESSAGE


@asynccontextmanager
async def refreshed_fc(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
):
    """IB 接続 -> FC refresh の共通処理。"""
    from avionics.calendar import as_of_for_bundle
    from avionics.ib import with_ib_market_data_service
    from cockpit.stack import build_cockpit_stack
    from store.db import get_connection
    from store.state import read_altitude_regime, read_target_futures

    conn = get_connection()
    try:
        altitude = read_altitude_regime(conn)
        target_base_by_symbol = read_target_futures(conn)
        async with with_ib_market_data_service(
            host, port, client_id=client_id, timeout=timeout
        ) as fetcher:
            fc, _ = build_cockpit_stack(symbols, altitude=altitude)
            as_of = as_of_for_bundle()
            await fc.refresh(fetcher, as_of, symbols, altitude=altitude)
            yield fc, fetcher, target_base_by_symbol
    finally:
        conn.close()


async def fetch_cockpit_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    from reports.format_cockpit_report import format_cockpit_report

    async with refreshed_fc(
        host, port, symbols, client_id=client_id, timeout=timeout
    ) as (fc, _fetcher, _targets):
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
    from reports.format_breakdown_report import format_breakdown_report

    async with refreshed_fc(
        host, port, symbols, client_id=client_id, timeout=timeout
    ) as (fc, _fetcher, _targets):
        return format_breakdown_report(fc)


async def fetch_daily_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    from reports.format_daily_report import format_daily_report

    async with refreshed_fc(
        host, port, symbols, client_id=client_id, timeout=timeout
    ) as (fc, fetcher, target_base_by_symbol):
        positions_detail = await fetcher.fetch_position_detail(symbols)
        return await format_daily_report(
            fc,
            symbols,
            positions_detail=positions_detail,
            target_base_by_symbol=target_base_by_symbol,
        )


async def fetch_position_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    from reports.format_position_report import format_position_report

    async with refreshed_fc(
        host, port, symbols, client_id=client_id, timeout=timeout
    ) as (fc, fetcher, target_base_by_symbol):
        positions_detail = await fetcher.fetch_position_detail(symbols)
        return await format_position_report(
            fc,
            symbols,
            positions_detail=positions_detail,
            target_base_by_symbol=target_base_by_symbol,
        )


async def fetch_health_report(
    host: str,
    port: int,
    *,
    client_id: int = 3,
) -> str:
    from avionics.ib import run_ib_healthcheck
    from reports.format_health_report import format_health_report

    out = await run_ib_healthcheck(host, port, client_id=client_id, timeout=30.0)
    return format_health_report(out)


async def fetch_schedule_alerts(host: str, port: int, symbols: list[str]) -> str:
    from avionics.ib import with_ib_connection
    from avionics.ib.services.schedule_service import IBScheduleService

    client_id = int(os.environ.get("IBKR_CLIENT_ID", "3"))
    async with with_ib_connection(host, port, client_id=client_id, timeout=30.0) as ib:
        results = await IBScheduleService(ib).run_daily_schedule_scan(symbols)
    lines = ["【取引時間スキャン】"]
    for symbol, messages in results:
        lines.append(f"\n{symbol}:")
        if messages:
            for m in messages:
                lines.append(f"  {m}")
        else:
            lines.append("  特記事項なし（明日以降の変化なし）")
    return "\n".join(lines)


async def notify_gateway_ready(application: Any) -> None:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        return
    host, port, _symbols, client_id, _timeout = env_host_port_symbols()
    from avionics.ib import check_ib_connection
    import asyncio

    for _ in range(3):
        ok = await check_ib_connection(host, port, client_id=client_id, timeout=30.0)
        if ok:
            bot = getattr(application, "bot", None)
            if bot:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Sputnik 起動完了。API 利用可能です。\n\n"
                    + COCKPIT_BOT_COMMANDS_MESSAGE,
                )
            return
        await asyncio.sleep(5)
