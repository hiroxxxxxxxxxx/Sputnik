"""
IB（ib_async）接続を局所化する窓口。

avionics.ib パッケージ以外では ib_async を import しない。
reports や scripts は with_ib_fetcher / with_ib_connection / check_ib_connection のみ使う。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Dict, Optional

from .fetcher import IBRawFetcher


@asynccontextmanager
async def _ib_session(
    host: str,
    port: int,
    *,
    client_id: int = 3,
    timeout: float = 30.0,
    wrap: Callable[[IB], Any] = lambda ib: ib,
) -> AsyncIterator[Any]:
    """IB に接続し、wrap(ib) の結果を yield する。抜けたら disconnect。"""
    try:
        from ib_async import IB  # type: ignore
    except ImportError as e:
        raise ImportError(
            "ib_async is required for avionics.ib session. Install with: pip install ib_async"
        ) from e

    ib = IB()
    await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=timeout)
    try:
        yield wrap(ib)
    finally:
        ib.disconnect()


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
    async with _ib_session(host, port, client_id=client_id, timeout=timeout, wrap=IBRawFetcher) as fetcher:
        yield fetcher


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
    async with _ib_session(host, port, client_id=client_id, timeout=timeout) as ib:
        yield ib


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
        from ib_async import IB  # type: ignore
    except ImportError:
        return False
    try:
        ib = IB()
        await ib.connectAsync(host=host, port=port, clientId=client_id, timeout=timeout)
        ib.disconnect()
        return True
    except Exception:
        return False


async def run_ib_healthcheck(
    host: str,
    port: int,
    *,
    client_id: int = 3,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    IB 接続の段階診断を返す。

    返却キー:
      - ib_connected: bool
      - historical_nq_ok: bool
      - historical_nq_bars: Optional[int]
      - historical_nq_error: Optional[str]
      - whatif_mgc_ok: bool
      - whatif_mgc_error: Optional[str]
      - overall: "OK" | "DEGRADED" | "FAIL"
    """
    out: Dict[str, Any] = {
        "ib_connected": False,
        "historical_nq_ok": False,
        "historical_nq_bars": None,
        "historical_nq_error": None,
        "whatif_mgc_ok": False,
        "whatif_mgc_error": None,
        "overall": "FAIL",
    }
    try:
        async with with_ib_connection(
            host, port, client_id=client_id, timeout=timeout
        ) as ib:
            out["ib_connected"] = True

            # historical (NQ) 最小チェック
            try:
                from ib_async import ContFuture  # type: ignore

                bars = await ib.reqHistoricalDataAsync(
                    ContFuture(symbol="NQ", exchange="CME", currency="USD"),
                    endDateTime="",
                    durationStr="3 D",
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=True,
                    timeout=12,
                )
                bars_len = len(bars) if bars is not None else 0
                out["historical_nq_bars"] = bars_len
                out["historical_nq_ok"] = bars_len >= 2
                if bars_len < 2:
                    out["historical_nq_error"] = f"insufficient bars: {bars_len}"
            except Exception as e:
                out["historical_nq_error"] = f"{type(e).__name__}: {e}"

            # whatIf (MGC) 最小チェック（権限不足なら失敗として表示）
            try:
                from ib_async import Future, MarketOrder  # type: ignore

                base = Future(symbol="MGC", exchange="COMEX", currency="USD")
                details = await ib.reqContractDetailsAsync(base)
                contract: Optional[Any] = None
                if details:
                    futs = [
                        getattr(d, "contract", None)
                        for d in details
                        if getattr(getattr(d, "contract", None), "secType", None)
                        == "FUT"
                    ]
                    if futs:
                        contract = sorted(
                            futs,
                            key=lambda c: str(
                                getattr(c, "lastTradeDateOrContractMonth", "")
                            ),
                        )[0]
                if contract is None:
                    raise ValueError("MGC contract not resolved")
                order = MarketOrder("BUY", 1)
                order.whatIf = True
                await ib.whatIfOrderAsync(contract, order)
                out["whatif_mgc_ok"] = True
            except Exception as e:
                out["whatif_mgc_error"] = f"{type(e).__name__}: {e}"

    except Exception:
        out["overall"] = "FAIL"
        return out

    hist_ok = bool(out["historical_nq_ok"])
    whatif_ok = bool(out["whatif_mgc_ok"])
    if hist_ok and whatif_ok:
        out["overall"] = "OK"
    elif out["ib_connected"]:
        out["overall"] = "DEGRADED"
    else:
        out["overall"] = "FAIL"
    return out
