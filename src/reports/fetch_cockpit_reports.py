"""
レポート文字列を返す公開 API。IB 接続・bundle 取得・FC 更新・formatter 呼び出しを一括で行う。

IB 接続は avionics.ib.with_ib_fetcher に委譲（ib モジュール依存は avionics.ib に局所化）。
Script（telegram_cockpit_bot 等）は host, port, symbols を渡すだけ。
定義書「Phase 5」参照。LAYER_SCRIPT_REPORTS_FC 改善案に基づく。
"""

from __future__ import annotations

from datetime import datetime, timezone


async def fetch_cockpit_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    """
    IB から Raw を取得し FC.refresh で最新状態に更新したうえで、計器レポート文字列を返す。
    接続失敗時は例外を投げる。
    """
    from avionics.ib import with_ib_fetcher
    from cockpit.stack import build_cockpit_stack
    from reports.format_cockpit_report import format_cockpit_report
    from util import as_of_for_bundle

    async with with_ib_fetcher(host, port, client_id=client_id, timeout=timeout) as fetcher:
        fc, _ = build_cockpit_stack(symbols)
        as_of = as_of_for_bundle()
        await fc.refresh(fetcher, as_of, symbols)
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
    """
    IB から Raw を取得し FC.refresh で bundle を組み立てたうえで、各因子の入力となる Layer 2 シグナル内訳を返す。
    接続失敗時は例外を投げる。
    """
    from avionics.ib import with_ib_fetcher
    from cockpit.stack import build_cockpit_stack
    from reports.format_breakdown_report import format_breakdown_report
    from util import as_of_for_bundle

    async with with_ib_fetcher(host, port, client_id=client_id, timeout=timeout) as fetcher:
        fc, _ = build_cockpit_stack(symbols)
        as_of = as_of_for_bundle()
        await fc.refresh(fetcher, as_of, symbols)
        return format_breakdown_report(fc)


async def fetch_daily_report(
    host: str,
    port: int,
    symbols: list[str],
    *,
    client_id: int = 3,
    timeout: float = 75.0,
) -> str:
    """
    IB から Raw を取得し FC.refresh で最新状態に更新したうえで、
    Daily Flight Log 形式のレポート文字列を返す。接続失敗時は例外を投げる。
    """
    from avionics.ib import with_ib_fetcher
    from cockpit.stack import build_cockpit_stack
    from reports.format_daily_report import format_daily_flight_log
    from util import as_of_for_bundle

    async with with_ib_fetcher(host, port, client_id=client_id, timeout=timeout) as fetcher:
        fc, _ = build_cockpit_stack(symbols)
        as_of = as_of_for_bundle()
        await fc.refresh(fetcher, as_of, symbols)
        return await format_daily_flight_log(fc, symbols, as_of=as_of)
