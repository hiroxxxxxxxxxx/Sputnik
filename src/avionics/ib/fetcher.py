"""
IB（ib_async）経由で Raw のみ取得する（Layer 1）。

IBRawFetcher は IB から Raw を取得し RawMarketSnapshot（NQ/GC固定DTO）として返す。SignalBundle は作らない。
SignalBundle は FC.refresh 経由で get_last_bundle() から取得する。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..data.raw_types import (
    PriceBar,
    PriceBar1h,
    RawCapitalSnapshot,
    VolatilitySeriesPoint,
)
from ..data.raw_market_snapshot import RawMarketSnapshot


def _bar_to_price_bar(bar: Any) -> PriceBar:
    """ib_async の BarData を PriceBar（日足）に変換する。"""
    d = getattr(bar, "date", date.today())
    if isinstance(d, datetime):
        bar_date = d.date()
    elif isinstance(d, date):
        bar_date = d
    else:
        bar_date = date.today()
    return PriceBar(
        date=bar_date,
        close=float(bar.close),
        high=float(bar.high),
        volume=float(bar.volume),
    )


def _bar_to_price_bar_1h(bar: Any) -> PriceBar1h:
    """ib_async の BarData を PriceBar1h に変換する。"""
    d = getattr(bar, "date", datetime.now(timezone.utc))
    if not isinstance(d, datetime):
        d = datetime(d.year, d.month, d.day, 16, 0, 0, tzinfo=timezone.utc) if isinstance(d, date) else datetime.now(timezone.utc)
    return PriceBar1h(
        bar_end=d,
        open=float(getattr(bar, "open", bar.close)),
        close=float(bar.close),
        high=float(bar.high),
        volume=float(bar.volume),
    )


def _contract_for_price(symbol: str) -> Any:
    """価格系列用の IB 契約。ContFuture + 根シンボル（NQ/GC）。"""
    from ib_async import ContFuture

    m = {"NQ": ("NQ", "CME", "USD"), "GC": ("GC", "COMEX", "USD")}
    if symbol in m:
        s, ex, cur = m[symbol]
        return ContFuture(symbol=s, exchange=ex, currency=cur)
    return ContFuture(symbol=symbol, exchange="SMART", currency="USD")


def _contract_for_volatility(symbol: str) -> Any:
    """ボラティリティ指数用。VXN/GVZ は IND。"""
    from ib_async import Index

    ex = "CBOE" if symbol in ("VXN", "VIX", "GVZ") else "SMART"
    return Index(symbol=symbol, exchange=ex, currency="USD")


def _contract_for_etf(symbol: str) -> Any:
    """ETF（HYG, LQD, TIP 等）用。"""
    from ib_async import Stock

    return Stock(symbol=symbol, exchange="SMART", currency="USD")


class IBRawFetcher:
    """
    ib_async の IB インスタンスを使い、Raw を非同期で取得する（Layer 1 のみ）。
    IB から Raw を取得し RawMarketSnapshot として返す。SignalBundle は作らない。
    """

    def __init__(self, ib: Any) -> None:
        self._ib = ib

    async def _fetch_historical(
        self,
        contract: Any,
        end_date: date,
        duration_str: str = "40 D",
        bar_size: str = "1 day",
    ) -> List[Any]:
        """IB 履歴バー取得の共通メソッド。生の BarData リストを返す。"""
        from ib_async import ContFuture
        from ib_async.util import formatIBDatetime

        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
        end_str = formatIBDatetime(end_dt)
        is_cont_future = isinstance(contract, ContFuture)
        return await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime="" if is_cont_future else end_str,
            durationStr=duration_str,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
            timeout=30,
        )

    async def _fetch_bars(
        self,
        contract: Any,
        end_date: date,
        duration_str: str = "40 D",
        bar_size: str = "1 day",
    ) -> List[PriceBar]:
        """日足の履歴を取得し PriceBar のリストで返す。"""
        bars = await self._fetch_historical(contract, end_date, duration_str, bar_size)
        return [_bar_to_price_bar(b) for b in bars]

    async def _fetch_bars_1h(
        self,
        contract: Any,
        end_date: date,
        duration_str: str = "5 D",
    ) -> List[PriceBar1h]:
        """1h足の履歴を取得。"""
        bars = await self._fetch_historical(contract, end_date, duration_str, "1 hour")
        return [_bar_to_price_bar_1h(b) for b in bars]

    async def _fetch_volatility_series(
        self, contract: Any, as_of: date, limit: int = 20
    ) -> List[VolatilitySeriesPoint]:
        """直近 limit 営業日分の (日付, 終値) を取得。"""
        bars = await self._fetch_bars(
            contract, as_of, duration_str="40 D", bar_size="1 day"
        )
        points: List[VolatilitySeriesPoint] = []
        for b in sorted(bars, key=lambda x: x.date):
            if b.date <= as_of:
                points.append((b.date, b.close))
        return points[-limit:] if len(points) > limit else points

    async def _fetch_account_summary(
        self,
        account: str = "",
        base_density: float = 1.0,
        as_of: Optional[date] = None,
    ) -> Optional[RawCapitalSnapshot]:
        """証拠金サマリから RawCapitalSnapshot を組み立てる。"""
        summary = await self._ib.accountSummaryAsync(account)
        by_tag: Dict[str, float] = {}
        for av in summary:
            try:
                by_tag[av.tag] = float(av.value)
            except (ValueError, TypeError):
                continue
        nlv = by_tag.get("NetLiquidation") or by_tag.get("EquityWithLoanValue") or 0.0
        mm = by_tag.get("MaintMarginReq") or by_tag.get("InitMarginReq") or 0.0
        if nlv <= 0:
            return None
        current_value = by_tag.get("GrossPositionValue") or nlv
        d = as_of or date.today()
        return RawCapitalSnapshot(
            as_of=d,
            mm=mm,
            nlv=nlv,
            base_density=base_density,
            current_value=current_value,
            futures_multiplier=1.0,
        )

    async def fetch_raw(
        self,
        as_of: date,
        price_symbols: List[str],
        *,
        volatility_symbols: Optional[Dict[str, str]] = None,
        liquidity_credit_hyg_symbol: str,
        liquidity_credit_lqd_symbol: str,
        liquidity_tip_symbol: Optional[str] = None,
        account: str = "",
        base_density: float = 1.0,
        v_recovery_params: Optional[Dict[str, dict]] = None,
    ) -> Tuple[RawMarketSnapshot, Optional[RawCapitalSnapshot]]:
        """
        IB から Raw を取得し、RawMarketSnapshot（NQ/GC固定DTO）として返す。
        Layer 2 計算は行わない。SignalBundle が欲しい場合は呼び出し側で build_signal_bundle を呼ぶ。

        :return: (RawMarketSnapshot, Optional[RawCapitalSnapshot])
        """
        vol_map = volatility_symbols or {s: "VXN" if s == "NQ" else "GVZ" for s in price_symbols}

        def _series_limit(sym: str) -> int:
            if not v_recovery_params or sym not in v_recovery_params:
                return 20
            th = v_recovery_params[sym]
            v1 = int(th.get("V1_confirm_days", 1))
            v2 = int(th.get("V2_confirm_days", 2))
            return max(v1, v2, 20)

        coros: List[Any] = []
        for sym in price_symbols:
            coros.append(self._fetch_bars(_contract_for_price(sym), as_of))
        for sym in price_symbols:
            coros.append(
                self._fetch_volatility_series(
                    _contract_for_volatility(vol_map[sym]), as_of, limit=_series_limit(sym)
                )
            )
        coros.append(
            self._fetch_account_summary(account=account, base_density=base_density, as_of=as_of)
        )
        coros.append(
            self._fetch_bars(_contract_for_etf(liquidity_credit_hyg_symbol), as_of)
        )
        coros.append(self._fetch_bars(_contract_for_etf(liquidity_credit_lqd_symbol), as_of))
        if liquidity_tip_symbol:
            coros.append(self._fetch_bars(_contract_for_etf(liquidity_tip_symbol), as_of))
        for sym in price_symbols:
            coros.append(
                self._fetch_bars_1h(_contract_for_price(sym), as_of, duration_str="5 D")
            )

        results = await asyncio.gather(*coros)
        idx = 0
        price_bars: Dict[str, List[PriceBar]] = {}
        for sym in price_symbols:
            price_bars[sym] = results[idx]
            idx += 1
        vol_series: Dict[str, List[VolatilitySeriesPoint]] = {}
        for sym in price_symbols:
            series = results[idx]
            idx += 1
            if series:
                vol_series[sym] = series
        capital: Optional[RawCapitalSnapshot] = results[idx]
        idx += 1
        credit_map: Dict[str, List[PriceBar]] = {}
        credit_map[liquidity_credit_hyg_symbol] = results[idx]
        idx += 1
        credit_map[liquidity_credit_lqd_symbol] = results[idx]
        idx += 1
        tip: List[PriceBar] = []
        if liquidity_tip_symbol:
            tip = results[idx]
            idx += 1
        bars_1h: Dict[str, List[PriceBar1h]] = {}
        for sym in price_symbols:
            bars_1h[sym] = results[idx]
            idx += 1

        snapshot = RawMarketSnapshot(
            as_of=as_of,
            nq_price_bars=list(price_bars.get("NQ", [])),
            gc_price_bars=list(price_bars.get("GC", [])),
            nq_price_bars_1h=list(bars_1h.get("NQ", [])),
            gc_price_bars_1h=list(bars_1h.get("GC", [])),
            nq_volatility_series=list(vol_series.get("NQ", [])),
            gc_volatility_series=list(vol_series.get("GC", [])),
            capital_snapshot=capital,
            credit_bars=credit_map,
            tip_bars=tip,
        )
        return snapshot, capital
