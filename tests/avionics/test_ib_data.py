"""
IBDataFetcher と CachedRawDataProvider のテスト。

実 IB 接続は行わず、モック IB で fetch_signal_bundle の組み立てと
CachedRawDataProvider の RawDataProvider 互換を検証する。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from avionics.acquisition.ib_fetcher import _bar_to_price_bar
from avionics.data.cache import CachedRawDataProvider
from avionics.data.raw import PriceBar, RawCapitalSnapshot
from avionics.ib_data import IBDataFetcher


def _run(coro):
    return asyncio.run(coro)


# --- _bar_to_price_bar ---


def test_bar_to_price_bar_from_date() -> None:
    """BarData の date が date のとき PriceBar に変換する。"""
    bar = MagicMock()
    bar.date = date(2025, 3, 1)
    bar.close = 100.5
    bar.high = 101.0
    bar.volume = 1000.0
    out = _bar_to_price_bar(bar)
    assert out.date == date(2025, 3, 1)
    assert out.close == 100.5
    assert out.high == 101.0
    assert out.volume == 1000.0


def test_bar_to_price_bar_from_datetime() -> None:
    """BarData の date が datetime のとき .date() で date に変換する。"""
    bar = MagicMock()
    bar.date = datetime(2025, 3, 1, 16, 0, 0, tzinfo=timezone.utc)
    bar.close = 99.0
    bar.high = 100.0
    bar.volume = 500.0
    out = _bar_to_price_bar(bar)
    assert out.date == date(2025, 3, 1)
    assert out.close == 99.0


# --- CachedRawDataProvider ---


def test_cached_raw_data_provider_price_series() -> None:
    """get_price_series はキャッシュした bars の直近 limit 本を返す。"""
    bars = [
        PriceBar(date=date(2025, 2, i), close=100.0 + i, high=101.0, volume=1000.0)
        for i in range(1, 6)
    ]
    cache = CachedRawDataProvider(_price_bars={"NQ": bars})
    out = cache.get_price_series("NQ", 2)
    assert len(out) == 2
    assert out[0].date == date(2025, 2, 4)
    assert out[1].date == date(2025, 2, 5)
    assert cache.get_price_series("GC", 10) == []


def test_cached_raw_data_provider_volatility_and_capital() -> None:
    """get_volatility_index / get_capital_snapshot はキャッシュを返す。"""
    cap = RawCapitalSnapshot(
        as_of=date(2025, 3, 1),
        mm=50_000.0,
        nlv=1_000_000.0,
        base_density=1.0,
    )
    cache = CachedRawDataProvider(
        _volatility_series={"NQ": [(date(2025, 2, 28), 18.0), (date(2025, 3, 1), 18.5)]},
        _capital_snapshot=cap,
    )
    assert cache.get_volatility_index("NQ", date(2025, 3, 1)) == 18.5
    assert cache.get_volatility_index("GC", date(2025, 3, 1)) is None
    snap = cache.get_capital_snapshot(date(2025, 3, 1))
    assert snap is not None
    assert snap.nlv == 1_000_000.0
    assert snap.mm == 50_000.0


def test_cached_raw_data_provider_credit_and_tip() -> None:
    """get_credit_series / get_tip_series はキャッシュを返す。"""
    tip_bars = [
        PriceBar(date=date(2025, 2, i), close=105.0, high=106.0, volume=2000.0)
        for i in range(1, 6)
    ]
    cache = CachedRawDataProvider(
        _credit_bars={"HYG": []},
        _tip_bars=tip_bars,
    )
    assert cache.get_credit_series("HYG", 5) == []
    out = cache.get_tip_series(3)
    assert len(out) == 3
    assert out[-1].date == date(2025, 2, 5)


# --- IBDataFetcher with mock IB ---


@pytest.fixture
def mock_ib():
    """reqHistoricalDataAsync がモック bars を返し、accountSummaryAsync がモック口座値を返す IB。"""
    ib = MagicMock()
    # 日足モック（2本以上あれば compute_price_signals が動く）
    mock_bars = [
        MagicMock(
            date=date(2025, 2, 28),
            close=100.0,
            high=101.0,
            low=99.0,
            volume=1000.0,
        ),
        MagicMock(
            date=date(2025, 3, 1),
            close=101.0,
            high=102.0,
            low=100.0,
            volume=1100.0,
        ),
    ]
    for b in mock_bars:
        b.close = float(getattr(b, "close", 0))
        b.high = float(getattr(b, "high", 0))
        b.volume = float(getattr(b, "volume", 0))

    async def req_hist(*args, **kwargs):
        return mock_bars

    ib.reqHistoricalDataAsync = AsyncMock(side_effect=req_hist)
    class AV:
        def __init__(self, account: str, tag: str, value: str, currency: str, modelCode: str):
            self.account = account
            self.tag = tag
            self.value = value
            self.currency = currency
            self.modelCode = modelCode

    acct_values = [
        AV("DU123", "NetLiquidation", "1000000", "USD", ""),
        AV("DU123", "MaintMarginReq", "80000", "USD", ""),
        AV("DU123", "GrossPositionValue", "500000", "USD", ""),
    ]
    ib.accountSummaryAsync = AsyncMock(return_value=acct_values)
    return ib


def test_fetch_signal_bundle_returns_signal_bundle(mock_ib) -> None:
    """fetch_signal_bundle は SignalBundle を返し、price_signals が入る。"""
    fetcher = IBDataFetcher(mock_ib)
    as_of = date(2025, 3, 1)
    bundle, _ = _run(
        fetcher.fetch_signal_bundle(
            as_of=as_of,
            price_symbols=["NQ"],
            liquidity_credit_symbol=None,
            liquidity_tip=False,
            base_density=1.0,
        )
    )
    assert bundle.price_signals.get("NQ") is not None
    assert bundle.price_signals["NQ"].symbol == "NQ"
    assert bundle.volatility_signals.get("NQ") is not None
    assert bundle.capital_signals is not None
    assert bundle.capital_signals.mm_over_nlv > 0
    assert bundle.liquidity_credit is None
    assert bundle.liquidity_tip is None


def test_fetch_signal_bundle_with_liquidity(mock_ib) -> None:
    """liquidity_credit_symbol / liquidity_tip 指定で C/R 用シグナルが入る。"""
    fetcher = IBDataFetcher(mock_ib)
    as_of = date(2025, 3, 1)
    bundle, _ = _run(
        fetcher.fetch_signal_bundle(
            as_of=as_of,
            price_symbols=["NQ"],
            liquidity_credit_symbol="HYG",
            liquidity_tip=True,
            base_density=1.0,
        )
    )
    assert bundle.liquidity_credit is not None
    assert bundle.liquidity_tip is not None
