from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, List

from ...data.raw_types import PriceBar, PriceBar1h, VolatilitySeriesPoint


def bar_to_price_bar(bar: Any) -> PriceBar:
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


def bar_to_price_bar_1h(bar: Any) -> PriceBar1h:
    """ib_async の BarData を PriceBar1h に変換する。"""
    d = getattr(bar, "date", datetime.now(timezone.utc))
    if not isinstance(d, datetime):
        d = (
            datetime(d.year, d.month, d.day, 16, 0, 0, tzinfo=timezone.utc)
            if isinstance(d, date)
            else datetime.now(timezone.utc)
        )
    return PriceBar1h(
        bar_end=d,
        open=float(getattr(bar, "open", bar.close)),
        close=float(bar.close),
        high=float(bar.high),
        volume=float(bar.volume),
    )


class IBMarketClient:
    """IB のマーケットデータ取得（historical / bars 変換）専用。"""

    def __init__(self, ib: Any) -> None:
        self._ib = ib

    async def fetch_historical(
        self,
        contract: Any,
        end_date: date,
        duration_str: str = "40 D",
        bar_size: str = "1 day",
    ) -> List[Any]:
        """IB 履歴バー取得の共通メソッド。生の BarData リストを返す。"""
        from ib_async import ContFuture
        from ib_async.util import formatIBDatetime

        end_dt = datetime(
            end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc
        )
        end_str = formatIBDatetime(end_dt)
        is_cont_future = isinstance(contract, ContFuture)
        try:
            bars = await self._ib.reqHistoricalDataAsync(
                contract,
                endDateTime="" if is_cont_future else end_str,
                durationStr=duration_str,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=True,
                timeout=30,
            )
        except Exception as exc:
            raise ValueError(
                "failed to fetch historical bars "
                f"(contract={contract!r}, end_date={end_date.isoformat()}, duration={duration_str}, bar_size={bar_size}): {exc}"
            ) from exc
        if bars is None:
            raise ValueError(
                "historical bars are None "
                f"(contract={contract!r}, end_date={end_date.isoformat()}, duration={duration_str}, bar_size={bar_size})"
            )
        return bars

    async def fetch_bars(
        self,
        contract: Any,
        end_date: date,
        duration_str: str = "40 D",
        bar_size: str = "1 day",
    ) -> List[PriceBar]:
        """日足の履歴を取得し PriceBar のリストで返す。"""
        bars = await self.fetch_historical(contract, end_date, duration_str, bar_size)
        return [bar_to_price_bar(b) for b in bars]

    async def fetch_bars_1h(
        self,
        contract: Any,
        end_date: date,
        duration_str: str = "5 D",
    ) -> List[PriceBar1h]:
        """1h足の履歴を取得。"""
        bars = await self.fetch_historical(contract, end_date, duration_str, "1 hour")
        return [bar_to_price_bar_1h(b) for b in bars]

    async def fetch_volatility_series(
        self, contract: Any, as_of: date, limit: int = 20
    ) -> List[VolatilitySeriesPoint]:
        """直近 limit 営業日分の (日付, 終値) を取得。"""
        bars = await self.fetch_bars(contract, as_of, duration_str="40 D", bar_size="1 day")
        points: List[VolatilitySeriesPoint] = []
        for b in sorted(bars, key=lambda x: x.date):
            if b.date <= as_of:
                points.append((b.date, b.close))
        return points[-limit:] if len(points) > limit else points
