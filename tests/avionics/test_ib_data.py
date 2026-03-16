"""
FC.refresh(DataSource) と get_last_bundle のテスト。

実 IB 接続は行わず、モック DataSource で refresh → get_last_bundle の組み立てと
CachedRawDataProvider の RawDataProvider 互換を検証する。
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock

import pytest

from avionics.data.cache import CachedRawDataProvider
from avionics.data.fc_signals import EngineFactorMapping
from avionics.data.raw import PriceBar, RawCapitalSnapshot
from avionics.data.source import BundleBuildOptions, DataSource
from avionics.flight_controller import FlightController
from avionics.ib.fetcher import _bar_to_price_bar


def _run(coro):
    return asyncio.run(coro)


# --- _bar_to_price_bar ---


def test_bar_to_price_bar_from_date() -> None:
    """BarData の date が date のとき PriceBar に変換する。"""
    bar = _mock_bar(date(2025, 3, 1), 100.5, 101.0, 1000.0)
    out = _bar_to_price_bar(bar)
    assert out.date == date(2025, 3, 1)
    assert out.close == 100.5
    assert out.high == 101.0
    assert out.volume == 1000.0


def test_bar_to_price_bar_from_datetime() -> None:
    """BarData の date が datetime のとき .date() で date に変換する。"""
    from datetime import datetime, timezone
    bar = _mock_bar(datetime(2025, 3, 1, 16, 0, 0, tzinfo=timezone.utc), 99.0, 100.0, 500.0)
    out = _bar_to_price_bar(bar)
    assert out.date == date(2025, 3, 1)
    assert out.close == 99.0


def _mock_bar(d, close: float, high: float, volume: float):
    from unittest.mock import MagicMock
    bar = MagicMock()
    bar.date = d
    bar.close = close
    bar.high = high
    bar.volume = volume
    return bar


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


# --- Mock DataSource + FC.refresh → get_last_bundle ---


class MockDataSource:
    """テスト用: 事前に用意した CachedRawDataProvider と RawCapitalSnapshot を返す DataSource。"""

    def __init__(
        self,
        cache: CachedRawDataProvider,
        capital_snapshot: Optional[RawCapitalSnapshot] = None,
    ) -> None:
        self._cache = cache
        self._capital_snapshot = capital_snapshot

    async def fetch_raw(
        self,
        as_of: date,
        price_symbols: List[str],
        *,
        volatility_symbols: Optional[Dict[str, str]] = None,
        liquidity_credit_symbol: Optional[str] = None,
        liquidity_tip: bool = True,
        account: str = "",
        base_density: float = 1.0,
        v_recovery_params: Optional[Dict[str, dict]] = None,
    ) -> Tuple[CachedRawDataProvider, Optional[RawCapitalSnapshot]]:
        return (self._cache, self._capital_snapshot)


def _make_fc(symbols: List[str], options: Optional[BundleBuildOptions] = None) -> FlightController:
    """因子なしの FC（refresh で bundle だけ組み立てる用）。"""
    mapping = EngineFactorMapping(
        symbol_factors={s: [] for s in symbols},
        limit_factors=[],
        global_market_factors=[],
    )
    return FlightController(
        mapping=mapping,
        bundle_build_options=options or BundleBuildOptions(),
    )


def test_fc_refresh_returns_bundle_with_price_and_capital() -> None:
    """fc.refresh(mock_ds) のあと get_last_bundle() で price_signals / capital_signals が入る。"""
    bars = [
        PriceBar(date=date(2025, 2, 28), close=100.0, high=101.0, volume=1000.0),
        PriceBar(date=date(2025, 3, 1), close=101.0, high=102.0, volume=1100.0),
    ]
    cap = RawCapitalSnapshot(
        as_of=date(2025, 3, 1),
        mm=80_000.0,
        nlv=1_000_000.0,
        base_density=1.0,
    )
    cache = CachedRawDataProvider(
        _price_bars={"NQ": bars},
        _volatility_series={"NQ": [(date(2025, 3, 1), 18.5)]},
        _capital_snapshot=cap,
    )
    ds = MockDataSource(cache, capital_snapshot=cap)
    fc = _make_fc(["NQ"])
    _run(fc.refresh(ds, date(2025, 3, 1), ["NQ"]))
    bundle = fc.get_last_bundle()
    assert bundle is not None
    assert bundle.price_signals.get("NQ") is not None
    assert bundle.price_signals["NQ"].symbol == "NQ"
    assert bundle.volatility_signals.get("NQ") is not None
    assert bundle.capital_signals is not None
    assert bundle.capital_signals.mm_over_nlv > 0
    assert bundle.liquidity_credit is None
    assert bundle.liquidity_tip is None
    assert fc.get_last_capital_snapshot() is cap


def test_fc_refresh_with_liquidity_options() -> None:
    """liquidity_credit_symbol / liquidity_tip 指定で C/R 用シグナルが bundle に入る。"""
    bars = [
        PriceBar(date=date(2025, 3, 1), close=101.0, high=102.0, volume=1100.0),
    ]
    tip_bars = [
        PriceBar(date=date(2025, 2, i), close=105.0, high=106.0, volume=2000.0)
        for i in range(1, 4)
    ]
    cache = CachedRawDataProvider(
        _price_bars={"NQ": bars},
        _volatility_series={"NQ": [(date(2025, 3, 1), 18.5)]},
        _credit_bars={"HYG": []},
        _tip_bars=tip_bars,
    )
    ds = MockDataSource(cache, capital_snapshot=None)
    options = BundleBuildOptions(
        liquidity_credit_symbol="HYG",
        liquidity_tip=True,
    )
    fc = _make_fc(["NQ"], options=options)
    _run(fc.refresh(ds, date(2025, 3, 1), ["NQ"]))
    bundle = fc.get_last_bundle()
    assert bundle is not None
    assert bundle.liquidity_credit is not None
    assert bundle.liquidity_tip is not None
